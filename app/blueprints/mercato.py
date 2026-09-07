import psycopg2
from app import telegram_utils
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from pydantic import ValidationError
from app.core.db import connessione
from app.blueprints.user import redirect_gate_chiuso

from app.core.logging import get_logger
from app.domini.calendario import anni_prestito_ammessi
from app.domini.ruoli import pulisci_ruolo
from app.repositories import aste as aste_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import draft as draft_repo
from app.schemas.scambio import PropostaScambio
from app.services import mercato as servizio_mercato
from app.repositories import giocatori as giocatori_repo
from app.repositories import squadre as squadre_repo
from app.repositories import vetrina as vetrina_repo

logger = get_logger(__name__)


mercato_bp = Blueprint('mercato', __name__, url_prefix='/mercato')


@mercato_bp.before_request
def blocca_mercato_chiuso():
    with connessione() as (conn, cur):
        if not configurazione_repo.mercato_aperto(cur):
            flash("❌ Il mercato scambi è chiuso.", "danger")
            return redirect_gate_chiuso()


def validate_pick_ids(pick_ids, conn):
    # Valida che gli ID delle pick esistano effettivamente nella tabella draft
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        return draft_repo.esistono_tutte(cur, pick_ids)


@mercato_bp.route("/mercato/<nome_squadra>", methods=["GET", "POST"])
def user_mercato(nome_squadra):
    crediti = 0
    offerta_massima_possibile = 0

    try:
        with connessione(isolamento=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ) as (conn, cur):
            if request.method == "POST":

                # Bottone ANNULLA scambio
                scambio_id = request.form.get("annulla_scambio")
                if scambio_id:
                    annulla_scambio(scambio_id, conn)


                # Bottone ACCETTA scambio
                scambio_id = request.form.get("accetta_scambio")
                if scambio_id:
                    effettua_scambio(scambio_id, conn, nome_squadra)
                

            
                # Bottone RIFIUTA scambio
                scambio_id = request.form.get("rifiuta_scambio")
                if scambio_id:
                    rifiuta_scambio(scambio_id, conn)


        
            crediti = squadre_repo.crediti(cur, nome_squadra)
            offerta_totale = aste_repo.offerta_totale(cur, nome_squadra)
            offerta_massima_possibile = crediti - offerta_totale

            scambi = servizio_mercato.scambi_della_squadra(cur, nome_squadra)
        
    except Exception:
        logger.exception("Errore")
        flash("❌ Errore durante il caricamento degli scambi.", "danger")
        return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))


    return render_template("user_mercato.html", nome_squadra=nome_squadra, crediti=crediti, offerta_massima_possibile=offerta_massima_possibile, scambi=scambi)


@mercato_bp.route("/visualizza_proposta/<scambio_id>", methods=["GET", "POST"])
def visualizza_proposta(scambio_id):
    with connessione() as (conn, cur):
        scambio = servizio_mercato.dettaglio_proposta(cur, scambio_id)

    if not scambio:
        flash("❌ Proposta non trovata.", "danger")
        return redirect(url_for("pubblico.home"))

    return render_template("visualizza_proposta.html", scambio=scambio)


@mercato_bp.route("/nuovo_scambio/<nome_squadra>", methods=["GET", "POST"])
def nuovo_scambio(nome_squadra):

    try:
        with connessione() as (conn, cur):
            if request.method == "POST":
                try:
                    proposta = PropostaScambio.da_form(
                        request.form, *anni_prestito_ammessi())
                except ValidationError:
                    flash("Seleziona una squadra destinataria.", "warning")
                    return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

                if proposta.e_vuota:
                    flash("La proposta non può essere completamente vuota: offri o richiedi almeno un giocatore, dei crediti, una pick o un prestito.", "warning")
                    return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

                # Le pick devono esistere davvero: lo schema valida la forma dei
                # dati, non la loro coerenza con lo stato del gioco.
                if not draft_repo.esistono_tutte(cur, proposta.pick_offerta):
                    flash("❌ Una o più pick offerte non valide.", "danger")
                    return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

                if not draft_repo.esistono_tutte(cur, proposta.pick_richiesta):
                    flash("❌ Una o più pick richieste non valide.", "danger")
                    return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

                # Il limite di due prestiti in entrata va verificato sulla squadra
                # che riceverebbe davvero il giocatore: chi lo chiede per i prestiti
                # richiesti, l'altra per quelli offerti.
                for squadra, quanti in ((nome_squadra, len(proposta.prestiti_richiesti)),
                                        (proposta.squadra_destinataria, len(proposta.prestiti_offerti))):
                    if quanti and giocatori_repo.slot_prestiti_in(cur, squadra) + quanti > 2:
                        flash(f"❌ {squadra} non ha abbastanza slot prestiti disponibili.", "danger")
                        return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

                id_scambio = servizio_mercato.crea_proposta(conn, cur, nome_squadra, proposta)

                conn.commit()


                flash("✅ Proposta inviata con successo!", "success")
                telegram_utils.nuovo_scambio(conn, id_scambio)

                return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))


            # Sezione GET

            # Recupera tutte le squadre (tranne "Svincolato")
            cur.execute('''
                SELECT nome, crediti 
                FROM squadra 
                WHERE nome <> 'Svincolato'
                ORDER BY nome;
            ''')
            squadre_raw = cur.fetchall()

            squadre = []
            crediti_effettivi = 0
            offerta_totale = aste_repo.offerta_totale(cur, nome_squadra)

            # Conteggi per TUTTE le squadre in poche query aggregate, invece di 4 query per squadra nel ciclo
            cur.execute('''
                SELECT squadra_att, COUNT(id) AS slot_giocatori
                FROM giocatore
                WHERE tipo_contratto IN ('Hold', 'Indeterminato')
                GROUP BY squadra_att;
            ''')
            slot_giocatori_map = {r["squadra_att"]: r["slot_giocatori"] for r in cur.fetchall()}

            cur.execute('''
                SELECT squadra, COUNT(*) AS slot_aste
                FROM asta, UNNEST(partecipanti) AS squadra
                WHERE stato <> 'conclusa'
                GROUP BY squadra;
            ''')
            slot_aste_map = {r["squadra"]: r["slot_aste"] for r in cur.fetchall()}

            cur.execute('''
                SELECT squadra_att, COUNT(id) AS slot_prestiti
                FROM giocatore
                WHERE tipo_contratto = 'Fanta-Prestito'
                GROUP BY squadra_att;
            ''')
            slot_prestiti_map = {r["squadra_att"]: r["slot_prestiti"] for r in cur.fetchall()}

            cur.execute('''
                SELECT squadra_vincente, SUM(ultima_offerta) AS offerta_totale
                FROM asta
                WHERE stato = 'in_corso'
                GROUP BY squadra_vincente;
            ''')
            offerta_totale_map = {r["squadra_vincente"]: r["offerta_totale"] or 0 for r in cur.fetchall()}

            def slot_occupati_squadra(nome):
                return int(slot_giocatori_map.get(nome, 0)) + int(slot_aste_map.get(nome, 0))

            for s in squadre_raw:
                slot_occupati = slot_occupati_squadra(s["nome"])
                slot_prestiti = int(slot_prestiti_map.get(s["nome"], 0))
                # Calcola l'offerta totale per la squadra corrente (non usare l'offerta della squadra loggata)
                offerta_totale_squadra = int(offerta_totale_map.get(s["nome"], 0))
                offerta_massima_possibile = max(s["crediti"] - offerta_totale_squadra, 0)

                squadre.append({
                    "nome": s["nome"],
                    "offerta_massima_possibile": offerta_massima_possibile,
                    "slot_liberi": max(30 - slot_occupati, 0),
                    "slot_prestiti": slot_prestiti
                })

                if s["nome"] == nome_squadra:
                    crediti_effettivi = offerta_massima_possibile

            # Slot liberi e prestiti della squadra loggata (riusa le mappe già calcolate sopra)
            slot_liberi_miei = max(30 - slot_occupati_squadra(nome_squadra), 0)
            slot_prestiti_miei = int(slot_prestiti_map.get(nome_squadra, 0))

            # Recupera tutti i giocatori validi (non svincolati, non prestiti, non hold)
            cur.execute('''
                    SELECT id, nome, squadra_att, tipo_contratto, ruolo, club
                    FROM giocatore
                    WHERE squadra_att IS NOT NULL
                        AND squadra_att != 'Svincolati'
                        AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold')
                    ORDER BY squadra_att, nome;
            ''')
            giocatori_raw = cur.fetchall()

            giocatori = [
                {
                    "id": g["id"],
                    "nome": g["nome"],
                    "squadra_att": g["squadra_att"],
                    "tipo_contratto": g["tipo_contratto"],
                    "ruolo": pulisci_ruolo(g["ruolo"]),
                    "club": g["club"]
                }
                for g in giocatori_raw
            ]
            miei_giocatori = [g for g in giocatori if g["squadra_att"] == nome_squadra]

            # Recupera tutte le pick dal draft
            cur.execute('''
                SELECT id, anno, giro, numero, detentore_att, detentore_originale
                    FROM draft
                WHERE id_giocatore_scelto IS NULL
                    ORDER BY anno, giro, numero;
            ''')
            pick_raw = cur.fetchall()

            def normalize_team_name(value):
                return (value or "").strip().casefold()

            def extract_year(value):
                if value is None:
                    return None
                return value.year if hasattr(value, "year") else value

            team_name_norm = normalize_team_name(nome_squadra)
            mie_pick = [
                {
                    "id": p["id"],
                    "anno": extract_year(p["anno"]),
                    "giro": p["giro"],
                    "numero": p["numero"],
                    "detentore_att": p["detentore_att"],
                    "detentore_originale": p["detentore_originale"]
                }
                for p in pick_raw
                if normalize_team_name(p["detentore_att"]) == team_name_norm
            ]
            pick_list = [
                {
                    "id": p["id"],
                    "anno": extract_year(p["anno"]),
                    "giro": p["giro"],
                    "numero": p["numero"],
                    "label": f"Giro {p['giro']}, Pick {p['numero']} ({p['detentore_att']})",
                    "detentore_att": p["detentore_att"],
                    "detentore_att_norm": normalize_team_name(p["detentore_att"])
                }
                for p in pick_raw
            ]

            anni_scadenza, anno_default_scadenza = anni_prestito_ammessi()

            return render_template(
                "user_nuovo_scambio.html",
                nome_squadra=nome_squadra,
                squadre=squadre,
                giocatori=giocatori,
                miei_giocatori=miei_giocatori,
                mie_pick=mie_pick,
                pick_list=pick_list,
                crediti_effettivi=crediti_effettivi,
                slot_liberi_miei=slot_liberi_miei,
                slot_prestiti_miei=slot_prestiti_miei,
                anni_scadenza=anni_scadenza,
                anno_default_scadenza=anno_default_scadenza
            )

    except Exception:
        logger.exception("Errore durante il caricamento di 'nuovo_scambio'")
        flash("❌ Si è verificato un errore nel caricamento della pagina.", "danger")
        return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))


def controlla_scambio(id, conn):

    valido = True
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Recupero dati dello scambio
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE id = %s
                    FOR UPDATE;''', (id,))
        scambio = cur.fetchone()

        if scambio['stato'] != 'in_attesa':
            return False

        
        squadra_proponente = scambio["squadra_proponente"]
        squadra_destinataria = scambio["squadra_destinataria"]
        crediti_offerti = scambio["crediti_offerti"] or 0
        crediti_richiesti = scambio["crediti_richiesti"] or 0
        giocatori_offerti = scambio["giocatori_offerti"] or []
        giocatori_richiesti = scambio["giocatori_richiesti"] or []
        pick_offerta = scambio["pick_offerta"] or []
        pick_richiesta = scambio["pick_richiesta"] or []

        # Controllo che le squadre abbiano abbastanza crediti per effettuare lo scambio
        cur.execute('''
                    SELECT crediti 
                    FROM squadra 
                    WHERE nome = %s FOR UPDATE;
        ''', (squadra_proponente,))

        crediti_prop = cur.fetchone()["crediti"]
        
        offerta_tot_prop = aste_repo.offerta_totale(cur, squadra_proponente)
        crediti_disp_prop = crediti_prop - offerta_tot_prop
        

        cur.execute('''
                    SELECT crediti 
                    FROM squadra 
                    WHERE nome = %s FOR UPDATE;
        ''', (squadra_destinataria,))
        crediti_dest = cur.fetchone()["crediti"]
        
        offerta_tot_dest = aste_repo.offerta_totale(cur, squadra_destinataria)
        crediti_disp_dest = crediti_dest - offerta_tot_dest

        if crediti_disp_prop < crediti_offerti:
            return False
        
        if crediti_disp_dest < crediti_richiesti:
            return False
        
        # Controllo che le squadre abbiano abbastanza slot giocatori disponibili per effettuare gli scambi
        slot_squadra_proponente = aste_repo.slot_occupati_totali(cur, squadra_proponente)
        slot_squadra_destinataria = aste_repo.slot_occupati_totali(cur, squadra_destinataria)

        # Verifica post-scambio: slot occupati dopo aver applicato entrate/uscite
        slot_prop_finali = slot_squadra_proponente - len(giocatori_offerti) + len(giocatori_richiesti)
        slot_dest_finali = slot_squadra_destinataria - len(giocatori_richiesti) + len(giocatori_offerti)

        if slot_prop_finali > 30:
            return False

        if slot_dest_finali > 30:
            return False

        return True

    except Exception:
        logger.exception("Errore")
        return False

    finally:
        cur.close()


def effettua_scambio(id, conn, nome_squadra):

    # Se lo scambio non è valido non fare niente
    if controlla_scambio(id, conn) == False:
        flash("❌ Non è possibile avviare questo scambio.", "danger")
        return
    

    # Se lo scambio è valido, esegui tutti i passaggi.
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupero dati dello scambio
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE id = %s
                        AND stato = 'in_attesa'
                    FOR UPDATE;''', (id,))
        
        scambio = cur.fetchone()

        if not scambio:
            raise ValueError(f"Nessuno scambio valido trovato con id: {id}")
        
        # Controllo se lo scambio è stato annullato nel mentre che la pagina era aperta
        if scambio['stato'] != 'in_attesa':
            flash("Lo scambio non è più valido.", "danger")
            return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))

        
        squadra_proponente = scambio["squadra_proponente"]
        squadra_destinataria = scambio["squadra_destinataria"]
        crediti_offerti = scambio["crediti_offerti"] or 0
        crediti_richiesti = scambio["crediti_richiesti"] or 0
        giocatori_offerti = scambio["giocatori_offerti"] or []
        giocatori_richiesti = scambio["giocatori_richiesti"] or []
        pick_offerta = scambio["pick_offerta"] or []
        pick_richiesta = scambio["pick_richiesta"] or []

        
        # Eseguo il trasferimento dei giocatori
        # Posso modificare sia squadra_att che detentore cartellino perchè non possono essere proposti scambi per giocatori in prestito o in hold.
        for giocatore_id in giocatori_offerti:
            cur.execute('''
                        UPDATE giocatore
                        SET detentore_cartellino = %s,
                            squadra_att = %s
                        WHERE id = %s;
            ''', (squadra_destinataria, squadra_destinataria, giocatore_id))

            # Annullo gli altri scambi in cui il giocatore è coinvolto
            cur.execute('''
                        UPDATE scambio
                        SET stato = 'annullato'
                        WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (giocatore_id, giocatore_id, id))
            
        for giocatore_id in giocatori_richiesti:
            cur.execute('''
                        UPDATE giocatore
                        SET detentore_cartellino = %s,
                            squadra_att = %s
                        WHERE id = %s;
            ''', (squadra_proponente, squadra_proponente, giocatore_id))

            # Annullo gli altri scambi in cui il giocatore è coinvolto
            cur.execute('''
                        UPDATE scambio
                        SET stato = 'annullato'
                        WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (giocatore_id, giocatore_id, id))

        # I giocatori scambiati decadono dalla vetrina, se presenti
        vetrina_repo.decadi(cur, giocatori_offerti + giocatori_richiesti)

        # Eseguo il trasferimento delle pick del draft
        for pick_id in pick_offerta:
            cur.execute('''
                        UPDATE draft
                        SET detentore_att = %s
                        WHERE id = %s;
            ''', (squadra_destinataria, pick_id))

        for pick_id in pick_richiesta:
            cur.execute('''
                        UPDATE draft
                        SET detentore_att = %s
                        WHERE id = %s;
            ''', (squadra_proponente, pick_id))
        
        # Aggiorno i crediti delle due squadre
        cur.execute('''
                    UPDATE squadra
                    SET crediti = crediti - %s + %s
                    WHERE nome = %s;
        ''', (crediti_offerti, crediti_richiesti, squadra_proponente))
        
        cur.execute('''
                    UPDATE squadra
                    SET crediti = crediti - %s + %s
                    WHERE nome = %s;
        ''', (crediti_richiesti, crediti_offerti, squadra_destinataria))
        
        
        # Aggiorno lo stato dello scambio
        cur.execute('''
                    UPDATE scambio
                    SET stato = 'accettato',
                    data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                    WHERE id = %s;
        ''', (id,))
        
        # Attiva eventuali prestiti collegati allo scambio
        prestiti_collegati = []
        if scambio and scambio['prestito_associato']:
            cur.execute('''
                        SELECT id, giocatore, squadra_ricevente, squadra_prestante
                        FROM prestito
                        WHERE id = ANY(%s) AND stato = 'in_attesa';
            ''', (scambio['prestito_associato'],))
            prestiti_collegati = cur.fetchall()
        
        for prestito in prestiti_collegati:
            # Attiva il prestito (stato = 'in_corso' come in attiva_prestito)
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'in_corso'
                        WHERE id = %s;
            ''', (prestito['id'],))
            
            # Aggiorna il contratto del giocatore in prestito
            cur.execute('''
                        UPDATE giocatore
                        SET tipo_contratto = 'Fanta-Prestito',
                            squadra_att = %s
                        WHERE id = %s;
            ''', (prestito['squadra_ricevente'], prestito['giocatore']))
            vetrina_repo.decadi(cur, prestito['giocatore'])

            # Rifiuta altri prestiti in attesa per lo stesso giocatore dalla stessa squadra prestante
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'rifiutato'
                        WHERE squadra_prestante = %s
                            AND giocatore = %s
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (prestito['squadra_prestante'], prestito['giocatore'], prestito['id']))
            
            # Annulla altri scambi che coinvolgono questo giocatore
            cur.execute('''
                        UPDATE scambio
                        SET stato = 'annullato'
                        WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (prestito['giocatore'], prestito['giocatore'], id))
        
        conn.commit()
        flash(f"✅ Scambio completato con successo tra {squadra_proponente} e {squadra_destinataria}", "success")
        telegram_utils.scambio_risposta(conn, id, "Accettato")
        return True
    
    except Exception:
        if conn:
            conn.rollback()
        logger.exception("Errore durante l'esecuzione dello scambio")
        flash("❌ Errore nell'esecuzione dello scambio. Rivedere i valori dello scambio.", "danger")
        return False
    
    finally:
        cur.close()
        
        
        
        
        
def annulla_scambio(scambio_id, conn):
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Recupera gli ID dei prestiti associati prima di annullare lo scambio
        cur.execute('''
                    SELECT prestito_associato, stato
                    FROM scambio 
                    WHERE id = %s
                    FOR UPDATE;
        ''', (scambio_id,))
        scambio = cur.fetchone()
        
        # Controllo se lo scambio è ancora annullabile
        if not scambio or scambio['stato'] != 'in_attesa':
            conn.rollback()
            return
        
        # Aggiorno lo stato
        cur.execute('''
                    UPDATE scambio 
                    SET stato = 'annullato' 
                    WHERE id = %s;
        ''', (scambio_id,))
        
        # Annulla anche i prestiti collegati, se ce ne sono
        if scambio and scambio['prestito_associato']:
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'annullato'
                        WHERE id = ANY(%s) AND stato = 'in_attesa';
            ''', (scambio['prestito_associato'],))
        
        conn.commit()
    
    except Exception:
        logger.exception("Errore durante l'annullamento dello scambio")
        conn.rollback()
        return False

    finally:
        cur.close()
        
        

def rifiuta_scambio(scambio_id, conn):

    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('''
                    SELECT prestito_associato 
                    FROM scambio 
                    WHERE id = %s
        ''', (scambio_id,))
        scambio = cur.fetchone()
        
        # Aggiorno lo stato
        cur.execute('''
                    UPDATE scambio
                    SET stato= 'rifiutato',
                        data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                    WHERE id = %s;
        ''', (scambio_id,))
        
        # Rifiuta anche i prestiti collegati
        if scambio and scambio['prestito_associato']:
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'rifiutato'
                        WHERE id = ANY(%s) AND stato = 'in_attesa';
            ''', (scambio['prestito_associato'],))
        conn.commit()
        telegram_utils.scambio_risposta(conn, scambio_id, "Rifiutato")
        
    except Exception:
        logger.exception("Errore durante il rifiuto dello scambio")
        conn.rollback()
    
    finally:
        cur.close()
