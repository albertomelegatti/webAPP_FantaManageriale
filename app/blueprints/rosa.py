import json
import math
import pytz
from app import telegram_utils
from datetime import datetime
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.core.db import connessione, resync_sequence
from app.core.formato import url_campioncino
from app.domini.ruoli import pulisci_ruolo, ruolo_sort_key

from app.core.logging import get_logger
from app.core.tempo import formatta_data
from app.repositories import aste as aste_repo
from app.repositories import prestiti as prestiti_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import richieste as richieste_repo
from app.services import rosa as servizio_rosa
from app.repositories import squadre as squadre_repo
from app.repositories import vetrina as vetrina_repo

logger = get_logger(__name__)

rosa_bp = Blueprint('rosa', __name__, url_prefix='/rosa')


@rosa_bp.route("/user_primavera/<nome_squadra>", methods=["GET", "POST"])
def user_primavera(nome_squadra):
    primavera = []

    with connessione() as (conn, cur):
        if request.method == "POST":

            # Promuovi un giocatore in prima squadra
            id_giocatore_da_promuovere = request.form.get("id_giocatore_da_promuovere")
            if id_giocatore_da_promuovere:
                giocatori_repo.cambia_tipo_contratto(cur, id_giocatore_da_promuovere, 'Indeterminato')
                conn.commit()

                nome_giocatore = giocatori_repo.nome(cur, id_giocatore_da_promuovere)
                flash("✅ Giocatore promosso in prima squadra con successo.", "success")
                telegram_utils.promozione_giocatore_primavera(conn, nome_squadra, nome_giocatore)

            # Taglia un giocatore dalla primavera
            id_giocatore_da_tagliare = request.form.get("id_giocatore_da_tagliare")
            if id_giocatore_da_tagliare:
                giocatori_repo.svincola(cur, id_giocatore_da_tagliare, 'Svincolato')
                vetrina_repo.decadi(cur, id_giocatore_da_tagliare)

                nome_giocatore = giocatori_repo.nome(cur, id_giocatore_da_tagliare)

                conn.commit()
                flash("✅ Giocatore tagliato con successo.", "success")
                telegram_utils.taglio_giocatore(conn, nome_squadra, nome_giocatore, 0)


        # Selezione dei giocatori in primavera
        primavera = servizio_rosa.giocatori_primavera(cur, nome_squadra)

    return render_template("user_primavera.html", nome_squadra=nome_squadra, primavera=primavera)


@rosa_bp.route("/user_vetrina/<nome_squadra>", methods=["GET", "POST"])
def user_vetrina(nome_squadra):

    rosa = []

    with connessione() as (conn, cur):
        if request.method == "POST":
            vetrina_data_raw = request.form.get("vetrina_data", "")

            try:
                dati_giocatori = json.loads(vetrina_data_raw) if vetrina_data_raw else []
            except (ValueError, TypeError):
                flash("❌ Dati inviati non validi, ricarica la pagina e riprova.", "danger")
                return redirect(url_for("rosa.user_vetrina", nome_squadra=nome_squadra))

            # Recupero i giocatori validi per questa squadra (id -> nome)
            giocatori_validi = {str(r['id']): r['nome']
                                for r in giocatori_repo.id_e_nome_con_cartellino(cur, nome_squadra)}

            # Validazione: nota inserita senza uno stato selezionato,
            # e scarto qualunque id non appartenente a questa squadra
            nomi_con_errore = []
            righe_valide = []
            for riga in dati_giocatori:
                id_giocatore = str(riga.get("id", ""))
                if id_giocatore not in giocatori_validi:
                    continue

                stato_vetrina = riga.get("stato") or ""
                nota_pulita = (riga.get("note") or "").strip()
                stato_valido = stato_vetrina and stato_vetrina != "rimuovi"

                if nota_pulita and not stato_valido:
                    nomi_con_errore.append(giocatori_validi[id_giocatore])

                righe_valide.append((id_giocatore, stato_vetrina, nota_pulita))

            if nomi_con_errore:
                flash(
                    f"❌ Seleziona uno stato vetrina prima di salvare una nota per: {', '.join(nomi_con_errore)}.",
                    "danger"
                )
                return redirect(url_for("rosa.user_vetrina", nome_squadra=nome_squadra))

            for id_giocatore, stato_vetrina, nota_pulita in righe_valide:

                # Valore sentinella dall'opzione "Rimuovi da vetrina":
                # trattalo come nessuno stato, uguale a stringa vuota
                if stato_vetrina == "rimuovi":
                    stato_vetrina = ""

                vetrina_esiste = vetrina_repo.esiste(cur, id_giocatore)

                if not stato_vetrina:
                    if vetrina_esiste:
                        vetrina_repo.rimuovi(cur, id_giocatore)
                    continue

                if vetrina_esiste:
                    vetrina_repo.aggiorna(cur, id_giocatore, stato_vetrina, nota_pulita or None)
                else:
                    vetrina_repo.crea(cur, id_giocatore, stato_vetrina, nota_pulita or None)

            conn.commit()
            flash("✅ Vetrina aggiornata con successo.", "success")
            return redirect(url_for("rosa.user_vetrina", nome_squadra=nome_squadra))


        # Sezione GET

        for giocatore in giocatori_repo.con_stato_vetrina(cur, nome_squadra):
            ruolo = pulisci_ruolo(giocatore['ruolo'])
            rosa.append({
                "id": giocatore["id"],
                "nome": giocatore["nome"],
                "ruolo": ruolo,
                "club": giocatore.get("club"),
                "campioncino": url_campioncino(giocatore.get("id_fantacalcio")),
                "quot_att_mantra": giocatore.get("quot_att_mantra"),
                "tipo_contratto": giocatore.get("tipo_contratto"),
                "stato_vetrina": giocatore.get("stato_vetrina"),
                "note": giocatore.get("note"),
            })

        rosa.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

    return render_template("user_vetrina.html", nome_squadra=nome_squadra, rosa=rosa)


@rosa_bp.route("/user_tagli/<nome_squadra>", methods=["GET", "POST"])
def user_tagli(nome_squadra):
    crediti = 0
    crediti_disponibili = 0
    rosa = []

    with connessione() as (conn, cur):
        crediti = squadre_repo.crediti(cur, nome_squadra)
        crediti_disponibili = crediti - aste_repo.offerta_totale(cur, nome_squadra)

        if request.method == "POST":
            id_giocatore_da_tagliare = request.form.get("id_giocatore_da_tagliare")
            if id_giocatore_da_tagliare:

                # Ottieni la quotazione attuale del giocatore
                quotazione_attuale = giocatori_repo.quotazione(cur, id_giocatore_da_tagliare)
                costo_taglio = math.ceil(quotazione_attuale / 2)

                if crediti_disponibili < costo_taglio:
                    flash("❌ Non hai abbastanza crediti per tagliare questo giocatore.", "danger")
                    conn.rollback()
                    return redirect(url_for("rosa.user_tagli", nome_squadra=nome_squadra))

                # Aggiorna il giocatore a svincolato
                giocatori_repo.svincola(cur, id_giocatore_da_tagliare, 'Svincolato')
                vetrina_repo.decadi(cur, id_giocatore_da_tagliare)

                # Aggiorna i crediti della squadra
                squadre_repo.aggiungi_crediti(cur, nome_squadra, -costo_taglio)

            
                nome_giocatore = giocatori_repo.nome(cur, id_giocatore_da_tagliare)

                conn.commit()
                flash(f"✅ Giocatore tagliato con successo! Costo: {costo_taglio} crediti.", "success")
                telegram_utils.taglio_giocatore(conn, nome_squadra, nome_giocatore, costo_taglio)
                return redirect(url_for("rosa.user_tagli", nome_squadra=nome_squadra))
        


        rosa = servizio_rosa.giocatori_tagliabili(cur, nome_squadra)

    return render_template("user_tagli.html", nome_squadra=nome_squadra, rosa=rosa, crediti=crediti, crediti_disponibili=crediti_disponibili)


@rosa_bp.route("/<nome_squadra>/richiesta_modifica_contratto/<id_giocatore>", methods=["GET", "POST"])
def richiesta_modifica_contratto(nome_squadra, id_giocatore):
    try:
        with connessione() as (conn, cur):
            if request.method == "POST":
                nuovo_tipo_contratto = request.form.get("nuovo_contratto")
                messaggio = (request.form.get("messaggio") or "").strip()

                # Retrocessione, Scadenza Contratto, Ritorno all'estero per fine prestito e Taglio
                # Gratuito sono varianti di "Trasferimento Reale" mostrate nel menu solo per
                # chiarezza: devono comportarsi esattamente come "Trasferimento Reale" (valore
                # 'Svincolato', unico valore ammesso dall'enum di database), con crediti a 0.
                tipi_contratto_come_trasferimento_reale = (
                    'Retrocessione',
                    'Scadenza Contratto',
                    "Ritorno all'estero per fine prestito",
                    'Taglio Gratuito'
                )
                if nuovo_tipo_contratto in tipi_contratto_come_trasferimento_reale:
                    crediti_richiesti = 0
                    nuovo_tipo_contratto = 'Svincolato'
                else:
                    crediti_richiesti = int(request.form.get("crediti_richiesti") or 0)

                tipo_contratto_attuale = giocatori_repo.tipo_contratto(cur, id_giocatore)

                def inserisci_richiesta(cursore):
                    richieste_repo.crea(cursore, id_giocatore, nuovo_tipo_contratto,
                                        nome_squadra, crediti_richiesti, messaggio)

                try:
                    inserisci_richiesta(cur)
                except pg_errors.UniqueViolation:
                    # La sequence dell'id è rimasta indietro rispetto ai dati (es. import/restore
                    # manuale sul DB). La riallineiamo e riproviamo, così l'utente non vede l'errore.
                    conn.rollback()
                    resync_sequence(conn, 'richiesta_modifica_contratto')
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    inserisci_richiesta(cur)

                conn.commit()

                flash("✅ Richiesta di modifica contratto inviata con successo.", "success")
                telegram_utils.richiesta_modifica_contratto(conn, nome_squadra, id_giocatore, messaggio)
                if tipo_contratto_attuale == 'Primavera':
                    return redirect(url_for("rosa.user_primavera", nome_squadra=nome_squadra))
                return redirect(url_for("rosa.user_tagli", nome_squadra=nome_squadra))

            giocatore_raw = giocatori_repo.dettaglio(cur, id_giocatore)

            if not giocatore_raw:
                flash(f"❌ Giocatore con id {id_giocatore} non trovato.", "danger")
                return redirect(url_for('rosa.user_tagli', nome_squadra=nome_squadra))

            nome_giocatore = giocatore_raw['nome']
            tipo_contratto = giocatore_raw['tipo_contratto']
            ruolo_giocatore = pulisci_ruolo(giocatore_raw['ruolo'])
            club_giocatore = giocatore_raw['club']

            return render_template("user_richiesta_modifica_contratto.html",
                                   nome_squadra=nome_squadra,
                                   nome_giocatore=nome_giocatore,
                                   tipo_contratto=tipo_contratto,
                                   ruolo_giocatore=ruolo_giocatore,
                                   club_giocatore=club_giocatore,
                                   id_giocatore=id_giocatore)

    except Exception:
        logger.exception("Errore durante la richiesta di modifica contratto")
        flash("❌ Errore durante la richiesta di modifica contratto.", "danger")
        return redirect(url_for('rosa.user_tagli', nome_squadra=nome_squadra))


@rosa_bp.route("/user_gestione_prestiti/<nome_squadra>", methods=["GET", "POST"])
def user_gestione_prestiti(nome_squadra):
    prestiti_in = []
    prestiti_out = []

    with connessione() as (conn, cur):
        if request.method == "POST":

            # Bottone RISCATTA GIOCATORE
            id_prestito_da_riscattare = request.form.get("riscatta_giocatore")
            if id_prestito_da_riscattare:
                riscatta_giocatore(conn, id_prestito_da_riscattare, nome_squadra)

            # Bottone RICHIESTA DI TERMINAZIONE ANTICIPATA
            id_prestito_per_cui_richiedere_terminazione = request.form.get("richiedi_terminazione")
            if id_prestito_per_cui_richiedere_terminazione:
                richiedi_terminazione_prestito(conn, id_prestito_per_cui_richiedere_terminazione, nome_squadra)


            # Bottone ACCETTA TERMINAZIONE ANTICIPATA
            id_prestito_da_terminare_ACCETTA = request.form.get("accetta_terminazione")
            if id_prestito_da_terminare_ACCETTA:
                accetta_terminazione(conn, id_prestito_da_terminare_ACCETTA)

            # Bottone RIFIUTA TERMINAZIONE ANTICIPATA
            id_prestito_da_terminare_RIFIUTA = request.form.get("rifiuta_terminazione")
            if id_prestito_da_terminare_RIFIUTA:
                rifiuta_terminazione(conn, id_prestito_da_terminare_RIFIUTA)


        # Ottengo i dati sui giocatori in prestito IN
        prestiti_in = []
        for p in prestiti_repo.in_corso_verso(cur, nome_squadra):
            prestiti_in.append({
                "id_prestito": p['id_prestito'],
                "giocatori": p['nome'],
                "ruolo": pulisci_ruolo(p['ruolo']),
                "club": p['club'],
                "squadra_prestante": p['squadra_prestante'],
                "squadra_ricevente": p['squadra_ricevente'],
                "stato": p['stato'],
                "data_inizio": formatta_data(p['data_inizio']),
                "data_fine": formatta_data(p['data_fine']),
                "richiedente_terminazione": p['richiedente_terminazione'],
                "note": p['note'],
                "costo_prestito": p['costo_prestito'],
                "tipo_prestito": p['tipo_prestito'],
                "crediti_riscatto": p['crediti_riscatto']
            })
    


        # Ottengo i dati sui giocatori in prestito OUT
        prestiti_out = []
        for p in prestiti_repo.in_corso_da(cur, nome_squadra):
            prestiti_out.append({
                "id_prestito": p['id_prestito'],
                "giocatori": p['nome'],
                "ruolo": pulisci_ruolo(p['ruolo']),
                "club": p['club'],
                "squadra_prestante": p['squadra_prestante'],
                "squadra_ricevente": p['squadra_ricevente'],
                "stato": p['stato'],
                "data_inizio": formatta_data(p['data_inizio']),
                "data_fine": formatta_data(p['data_fine']),
                "richiedente_terminazione": p['richiedente_terminazione'],
                "note": p['note'],
                "costo_prestito": p['costo_prestito'],
                "tipo_prestito": p['tipo_prestito'],
                "crediti_riscatto": p['crediti_riscatto']
            })

        slot_giocatori = giocatori_repo.slot_occupati_da_giocatori(cur, nome_squadra)

    return render_template("user_gestione_prestiti.html", nome_squadra=nome_squadra, prestiti_in=prestiti_in, prestiti_out=prestiti_out, slot_giocatori=slot_giocatori)


def riscatta_giocatore(conn, id_prestito, nome_squadra):
    """
    Riscatta un giocatore in prestito con diritto di riscatto.
    La squadra attuale (squadra_ricevente) paga i crediti del riscatto
    e il giocatore diventa di proprietà della squadra attuale.
    """
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupero informazioni sul prestito
        prestito = prestiti_repo.per_id(cur, id_prestito)

        if not prestito:
            flash("❌ Prestito non trovato.", "danger")
            return

        # Verifica che il prestito sia in corso
        if prestito['stato'] != 'in_corso':
            flash("❌ Il prestito non è in corso.", "danger")
            return

        # Verifica che il tipo sia "Con diritto di riscatto" o "Con obbligo di riscatto"
        if prestito['tipo_prestito'] not in ('obbligo_di_riscatto', 'diritto_di_riscatto'):
            flash("❌ Questo prestito non ha diritto di riscatto.", "danger")
            return

        # Controlla i crediti della squadra
        crediti_squadra = squadre_repo.crediti_se_esiste(cur, nome_squadra)

        if crediti_squadra is None:
            flash("❌ Squadra non trovata.", "danger")
            return

        costo_riscatto = prestito['crediti_riscatto']

        if crediti_squadra < costo_riscatto:
            flash(f"❌ Non hai abbastanza crediti per riscattare questo giocatore. Hai {crediti_squadra} crediti, te ne servono {costo_riscatto}.", "danger")
            return

        # RISCATTO EFFETTUATO:
            
        # 1. Sottrarre i crediti dalla squadra ricevente e aggiungerli alla squadra prestante
        squadre_repo.sposta_crediti(cur, prestito['squadra_ricevente'], prestito['squadra_prestante'], prestito['crediti_riscatto'])
        
        # 2. Aggiornare il prestito come "riscattato"
        prestiti_repo.termina(cur, id_prestito)

        # 3. Aggiornare il giocatore: squadra_att e detentore_cartellino diventano la squadra attuale
        giocatori_repo.trasferisci_dopo_riscatto(cur, prestito['giocatore'], nome_squadra)
        vetrina_repo.decadi(cur, prestito['giocatore'])

        conn.commit()
        flash(f"✅ Giocatore riscattato con successo! Pagati {costo_riscatto} crediti.", "success")
        telegram_utils.riscatto_giocatore(conn, id_prestito)

    except Exception:
        logger.exception("❌ Errore durante il riscatto del giocatore")
        flash("❌ Si è verificato un errore durante il riscatto. Ricaricare la pagina.", "danger")
        conn.rollback()

    finally:
        cur.close()


def richiedi_terminazione_prestito(conn, id_prestito, nome_squadra):
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Prima controllo che l'altra squadra non abbia già effettuato una richiesta di terminazione
        stato_prestito = prestiti_repo.stato(cur, id_prestito)

        if stato_prestito == 'richiesta_di_terminazione':
            flash("❌ L'altra squadra ha già richiesto una terminazione anticipata per questo giocatore. Aggiornare la pagina", "danger")
            return              # Il finally viene eseguito comunque

        # Se lo stato è 'in_corso' allora cambialo in 'richiesta_di_terminazione'
        prestiti_repo.richiedi_terminazione(cur, id_prestito, nome_squadra)
        conn.commit()
        flash("✅ Richiesta di terminazione anticipata inviata con successo.", "success")
        telegram_utils.richiesta_terminazione_prestito(conn, id_prestito)


    except Exception:
        logger.exception("Errore")
        flash("❌ Errore nel controllo del prestito, riprovare.", "danger")

    finally:
        cur.close()


def accetta_terminazione(conn, id_prestito):

    rome_tz = pytz.timezone("Europe/Rome")
    
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Controllo che il prestito non sia terminato mentre la pagina era aperta
        row = prestiti_repo.data_fine(cur, id_prestito)

        if row is None:
            flash("❌ Prestito non trovato.", "danger")
            return

        data_fine = row['data_fine']

        now = datetime.now(rome_tz)

        if data_fine and data_fine < now:
            flash("Il prestito è già terminato.", "warning")
            return

        # Modifico lo stato del prestito e imposto la data di fine prestito
        prestiti_repo.termina(cur, id_prestito)

        # Prima di modificare le imformazioni sul giocatore coinvolto, recupero le info sulle squadre coinvolte nel prestito
        row = prestiti_repo.giocatore_e_prestante(cur, id_prestito)

        # Modifico le info sul giocatore
        giocatori_repo.trasferisci_da_prestito(cur, row['giocatore'], row['squadra_prestante'])
        vetrina_repo.decadi(cur, row['giocatore'])

        conn.commit()
        flash("✅ Prestito terminato con successo.", "success")
        telegram_utils.richiesta_terminazione_prestito_risposta(conn, id_prestito, "Accettato")


    except Exception:
        logger.exception("Errore")
        flash("❌ Si è verificato un errore. Ricaricare la pagina.", "danger")

    finally:
        cur.close()


def rifiuta_terminazione(conn, id_prestito):

    rome_tz = pytz.timezone("Europe/Rome")
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Controllo che il prestito non sia terminato mentre la pagina era aperta
        row = prestiti_repo.data_fine(cur, id_prestito)

        if row is None:
            flash("❌ Prestito non trovato.", "danger")
            return

        data_fine = row['data_fine']

        now = datetime.now(rome_tz)

        if data_fine and data_fine < now:
            flash("Il prestito è già terminato.", "warning")
            return

        # Rimetto il prestito nel suo stato 'in_corso'
        prestiti_repo.annulla_richiesta_terminazione(cur, id_prestito)
        conn.commit()

        flash("✅ Richiesta di terminazione anticipata rifiutata con successo.", "success")
        telegram_utils.richiesta_terminazione_prestito_risposta(conn, id_prestito, "Rifiutato")


    except Exception:
        logger.exception("Errore")
        flash("❌ Si è verificato un errore. Ricaricare la pagina.", "danger")

    finally:
        cur.close()
