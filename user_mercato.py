import psycopg2
import telegram_utils
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from db import get_connection, release_connection
from user import format_giocatori, formatta_data
from queries import get_crediti_squadra, get_offerta_totale, get_slot_occupati


mercato_bp = Blueprint('mercato', __name__, url_prefix='/mercato')


@mercato_bp.route("/mercato/<nome_squadra>", methods=["GET", "POST"])
def user_mercato(nome_squadra):
    conn = None
    cur = None
    crediti = 0
    offerta_massima_possibile = 0

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Bottone ANNULLA scambio
            scambio_id = request.form.get("annulla_scambio")
            if scambio_id:
                cur.execute('''
                            UPDATE scambio
                            SET stato = 'annullato' 
                            WHERE id = %s;
                ''', (scambio_id,))
                conn.commit()


            # Bottone ACCETTA scambio
            scambio_id = request.form.get("accetta_scambio")
            if scambio_id:
                effettua_scambio(scambio_id, conn, nome_squadra)

            
            # Bottone RIFIUTA scambio
            scambio_id = request.form.get("rifiuta_scambio")
            if scambio_id:
                cur.execute('''
                            UPDATE scambio
                            SET stato= 'rifiutato',
                                data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                            WHERE id = %s;
                ''', (scambio_id,))
                conn.commit()




        
        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        offerta_massima_possibile = crediti - offerta_totale

        scambi_raw = []
        scambi = []

        # Scarico le informazioni sugli scambi della squadra loggata
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE squadra_proponente = %s
                    OR squadra_destinataria = %s;
        ''', (nome_squadra, nome_squadra))
        scambi_raw = cur.fetchall()

        for s in scambi_raw:

            valido = None
            if s['squadra_destinataria'] == nome_squadra and s['stato'] == 'in_attesa':
                valido = controlla_scambio(s['id'], conn)

            scambi.append({
                "scambio_id": s['id'],
                "squadra_proponente": s['squadra_proponente'],
                "squadra_destinataria": s['squadra_destinataria'],
                "giocatori_offerti": format_giocatori(s['giocatori_offerti']),
                "giocatori_richiesti": format_giocatori(s['giocatori_richiesti']),
                "crediti_offerti": s['crediti_offerti'],
                "crediti_richiesti": s['crediti_richiesti'],
                "messaggio": s['messaggio'],
                "stato": s['stato'],
                "data_proposta": formatta_data(s['data_proposta']),
                "data_risposta": formatta_data(s['data_risposta']),
                "valido": valido
            })
        
    except Exception as e:
        print("Errore:", e)
        flash("❌ Errore durante il caricamento degli scambi.", "danger")
        return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))

    finally:
        release_connection(conn, cur)

    return render_template("user_mercato.html", nome_squadra=nome_squadra, crediti=crediti, offerta_massima_possibile=offerta_massima_possibile, scambi=scambi)




@mercato_bp.route("/nuovo_scambio/<nome_squadra>", methods=["GET", "POST"])
def nuovo_scambio(nome_squadra):
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            squadra_destinataria = request.form.get("squadra_destinataria")
            crediti_offerti = int(request.form.get("crediti_offerti") or 0)
            crediti_richiesti = int(request.form.get("crediti_richiesti") or 0)
            giocatori_offerti = [int(g) for g in request.form.getlist("giocatori_offerti") if g.isdigit()]
            giocatori_richiesti = [int(g) for g in request.form.getlist("giocatori_richiesti") if g.isdigit()]
            messaggio = (request.form.get("messaggio") or "").strip()

            # Validazioni base
            if not squadra_destinataria:
                flash("Seleziona una squadra destinataria.", "warning")
                return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

            if not giocatori_offerti and crediti_offerti == 0:
                flash("Devi offrire almeno un giocatore o dei crediti.", "warning")
                return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

            if not giocatori_richiesti and crediti_richiesti == 0:
                flash("Devi richiedere almeno un giocatore o dei crediti.", "warning")
                return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

            # Inserisci la proposta di scambio
            cur.execute('''
                INSERT INTO scambio (
                    squadra_proponente, squadra_destinataria, 
                    crediti_offerti, crediti_richiesti, 
                    giocatori_offerti, giocatori_richiesti, 
                    messaggio, stato, data_proposta
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'in_attesa', NOW() AT TIME ZONE 'Europe/Rome')
                RETURNING id;
            ''', (
                nome_squadra,
                squadra_destinataria,
                crediti_offerti,
                crediti_richiesti,
                giocatori_offerti,
                giocatori_richiesti,
                messaggio
            ))
            id_scambio = cur.fetchone()['id']

            conn.commit()
            flash("✅ Proposta di scambio inviata con successo!", "success")
            # telegram_utils.nuovo_scambio(conn, id_scambio)
            return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))



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
        offerta_totale = get_offerta_totale(conn, nome_squadra)

        for s in squadre_raw:
            slot_occupati = int(get_slot_occupati(conn, s["nome"]))
            offerta_massima_possibile = max(s["crediti"] - offerta_totale, 0)

            squadre.append({
                "nome": s["nome"],
                "offerta_massima_possibile": offerta_massima_possibile,
                "slot_liberi": max(30 - slot_occupati, 0)
            })

            if s["nome"] == nome_squadra:
                crediti_effettivi = offerta_massima_possibile

        # Slot liberi della squadra loggata
        slot_liberi_miei = max(30 - int(get_slot_occupati(conn, nome_squadra)), 0)

        # Recupera tutti i giocatori validi (non svincolati, non prestiti, non hold)
        cur.execute('''
            SELECT id, nome, squadra_att
            FROM giocatore
            WHERE squadra_att IS NOT NULL
              AND squadra_att != 'Svincolati'
              AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold')
            ORDER BY squadra_att, nome;
        ''')
        giocatori_raw = cur.fetchall()

        miei_giocatori = [g for g in giocatori_raw if g["squadra_att"] == nome_squadra]
        giocatori = [
            {"id": g["id"], "nome": g["nome"], "squadra_att": g["squadra_att"]}
            for g in giocatori_raw
        ]

        return render_template(
            "user_nuovo_scambio.html",
            nome_squadra=nome_squadra,
            squadre=squadre,
            giocatori=giocatori,
            miei_giocatori=miei_giocatori,
            crediti_effettivi=crediti_effettivi,
            slot_liberi_miei=slot_liberi_miei
        )

    except Exception as e:
        print(f"Errore durante il caricamento di 'nuovo_scambio': {e}")
        flash("❌ Si è verificato un errore nel caricamento della pagina.", "danger")
        return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))

    finally:
        release_connection(conn, cur)



def controlla_scambio(id, conn):

    print(f"Controllo scambio: {id}")

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

        # Controllo che le squadre abbiano abbastanza crediti per effettuare lo scambio
        cur.execute('''
                    SELECT crediti 
                    FROM squadra 
                    WHERE nome = %s FOR UPDATE;
        ''', (squadra_proponente,))

        crediti_prop = cur.fetchone()["crediti"]
        
        offerta_tot_prop = get_offerta_totale(conn, squadra_proponente)
        crediti_disp_prop = crediti_prop - offerta_tot_prop
        

        cur.execute('''
                    SELECT crediti 
                    FROM squadra 
                    WHERE nome = %s FOR UPDATE;
        ''', (squadra_destinataria,))
        crediti_dest = cur.fetchone()["crediti"]
        
        offerta_tot_dest = get_offerta_totale(conn, squadra_destinataria)
        crediti_disp_dest = crediti_dest - offerta_tot_dest

        if crediti_disp_prop < crediti_offerti:
            return False
        
        if crediti_disp_dest < crediti_richiesti:
            return False
        
        # Controllo che le squadre abbiano abbastanza slot giocatori disponibili per effettuare gli scambi
        slot_squadra_proponente = get_slot_occupati(conn, squadra_proponente)
        num_giocatori_in_entrata = len(giocatori_richiesti)
        if slot_squadra_proponente + num_giocatori_in_entrata > 30:
            return False
        

        slot_squadra_destinataria = get_slot_occupati(conn, squadra_destinataria)
        num_giocatori_in_uscita = len(giocatori_offerti)
        if slot_squadra_destinataria + num_giocatori_in_uscita > 30:
            return False

        return True

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)





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
        
        conn.commit()
        print(f"✅ Scambio completato con successo tra {squadra_proponente} e {squadra_destinataria}")
        return True
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Errore durante l'esecuzione dello scambio: {e}")
        flash("❌ Errore nell'esecuzione dello scambio. Rivedere i valori dello scambio.", "danger")
        return False
    
    finally:
        # La connessione è None perchè viene rilasciata dalla pagina del mercato
        release_connection(None, cur)
