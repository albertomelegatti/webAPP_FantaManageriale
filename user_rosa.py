import math
import pytz
import telegram_utils
from datetime import datetime
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from db import get_connection, release_connection
from user import formatta_data
from queries import get_crediti_squadra, get_offerta_totale, get_quotazione_attuale, get_slot_giocatori, get_nome_giocatore

rosa_bp = Blueprint('rosa', __name__, url_prefix='/rosa')

@rosa_bp.route("/gestione_rosa/<nome_squadra>")
def user_gestione_rosa(nome_squadra):
    return render_template("user_gestione_rosa.html", nome_squadra=nome_squadra)


@rosa_bp.route("/user_primavera/<nome_squadra>", methods=["GET", "POST"])
def user_primavera(nome_squadra):
    conn = None
    cur = None
    primavera = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Promuovi un giocatore in prima squadra
            id_giocatore_da_promuovere = request.form.get("id_giocatore_da_promuovere")
            if id_giocatore_da_promuovere:
                cur.execute('''
                            UPDATE giocatore
                            SET tipo_contratto = 'Indeterminato'
                            WHERE id = %s;
                ''', (id_giocatore_da_promuovere,))
                conn.commit()

                nome_giocatore = get_nome_giocatore(conn, id_giocatore_da_promuovere)
                flash("✅ Giocatore promosso in prima squadra con successo.", "success")
                telegram_utils.promozione_giocatore_primavera(conn, nome_squadra, nome_giocatore)


        # Selezione dei giocatori in primavera
        cur.execute('''
                    SELECT id, nome, ruolo, quot_att_mantra
                    FROM giocatore
                    WHERE squadra_att = %s
                    AND tipo_contratto = 'Primavera';
        ''', (nome_squadra,))
        primavera_raw = cur.fetchall()

        primavera = []
        for p in primavera_raw:
            ruolo = p['ruolo'].strip("{}")
            primavera.append({
                "id": p['id'],
                "nome": p['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": p['quot_att_mantra']
            })

    except Exception as e:
        print(f"Errore durante il caricamento della primavera.")
        flash("❌ Errore durante il caricamento della primavera.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_primavera.html", nome_squadra=nome_squadra, primavera=primavera)





@rosa_bp.route("/user_tagli/<nome_squadra>", methods=["GET", "POST"])
def user_tagli(nome_squadra):
    conn = None
    cur = None
    crediti = 0
    crediti_disponibili = 0
    rosa = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        crediti = get_crediti_squadra(conn, nome_squadra)
        crediti_disponibili = crediti - get_offerta_totale(conn, nome_squadra)

        if request.method == "POST":
            id_giocatore_da_tagliare = request.form.get("id_giocatore_da_tagliare")
            if id_giocatore_da_tagliare:

                # Ottieni la quotazione attuale del giocatore
                quotazione_attuale = get_quotazione_attuale(conn, id_giocatore_da_tagliare)
                costo_taglio = math.ceil(quotazione_attuale / 2)

                if crediti_disponibili < costo_taglio:
                    flash("❌ Non hai abbastanza crediti per tagliare questo giocatore.", "danger")
                    conn.rollback()
                    return redirect(url_for("rosa.user_tagli", nome_squadra=nome_squadra))

                # Aggiorna il giocatore a svincolato
                cur.execute('''
                            UPDATE giocatore
                            SET squadra_att = 'Svincolato',
                                detentore_cartellino = 'Svincolato',
                                tipo_contratto = 'Svincolato'
                            WHERE id = %s;
                ''', (id_giocatore_da_tagliare,))

                # Aggiorna i crediti della squadra
                cur.execute('''
                            UPDATE squadra
                            SET crediti = crediti - %s
                            WHERE nome = %s;
                ''', (costo_taglio, nome_squadra))

                
                nome_giocatore = get_nome_giocatore(conn, id_giocatore_da_tagliare)

                conn.commit()
                flash(f"✅ Giocatore tagliato con successo! Costo: {costo_taglio} crediti.", "success")
                telegram_utils.taglio_giocatore(conn, nome_squadra, nome_giocatore, costo_taglio)
                return redirect(url_for("rosa.user_tagli", nome_squadra=nome_squadra))
            




        cur.execute('''
                    SELECT id, nome, ruolo, quot_att_mantra
                    FROM giocatore
                    WHERE squadra_att = %s 
                        AND tipo_contratto = 'Indeterminato'
                    ORDER BY ruolo, nome;
        ''', (nome_squadra,))
        rosa_raw = cur.fetchall()

        rosa = []
        for r in rosa_raw:
            ruolo = r['ruolo'].strip("{}")
            rosa.append({
                "id": r['id'],
                "nome": r['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": r['quot_att_mantra']
            })

    except Exception as e:
        print(f"Errore durante il caricamento o il taglio dei giocatori: {e}")
        flash("❌ Errore durante il caricamento o il taglio dei giocatori.", "danger")
        if conn:
            conn.rollback()

    finally:
        release_connection(conn, cur)

    return render_template("user_tagli.html", nome_squadra=nome_squadra, rosa=rosa, crediti=crediti, crediti_disponibili=crediti_disponibili)










@rosa_bp.route("/user_gestione_prestiti/<nome_squadra>", methods=["GET", "POST"])
def user_gestione_prestiti(nome_squadra):
    conn = None
    cur = None
    prestiti_in = []
    prestiti_out = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

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
        cur.execute('''
                    SELECT 
                        p.id AS id_prestito,
                        g.id AS id_giocatore,
                        *
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.squadra_ricevente = %s
                        AND p.stato IN ('in_corso', 'richiesta_di_terminazione');
        ''', (nome_squadra,))
        prestiti_in_raw = cur.fetchall()
        

        prestiti_in = []

        for p in prestiti_in_raw:
            prestiti_in.append({
                "id_prestito": p['id_prestito'],
                "giocatori": p['nome'],
                "squadra_prestante": p['squadra_prestante'],
                "squadra_ricevente": p['squadra_ricevente'],
                "stato": p['stato'],
                "data_inizio": formatta_data(p['data_inizio']),
                "data_fine": formatta_data(p['data_fine']),
                "richiedente_terminazione": p['richiedente_terminazione']
            })
        


        # Ottengo i dati sui giocatori in prestito OUT
        cur.execute('''
                    SELECT 
                        p.id AS id_prestito,
                        g.id AS id_giocatore,
                        *
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.squadra_prestante = %s
                        AND stato IN ('in_corso', 'richiesta_di_terminazione');
        ''', (nome_squadra,))
        prestiti_out_raw = cur.fetchall()

        prestiti_out = []

        for p in prestiti_out_raw:
            prestiti_out.append({
                "id_prestito": p['id_prestito'],
                "giocatori": p['nome'],
                "squadra_prestante": p['squadra_prestante'],
                "squadra_ricevente": p['squadra_ricevente'],
                "stato": p['stato'],
                "data_inizio": formatta_data(p['data_inizio']),
                "data_fine": formatta_data(p['data_fine']),
                "richiedente_terminazione": p['richiedente_terminazione']
            })

        slot_giocatori = get_slot_giocatori(conn, nome_squadra)
        


    except Exception as e:
        print(f"Errore: {e}")
        flash("❌ Si è verificato un errore. Ricaricare la pagina.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_gestione_prestiti.html", nome_squadra=nome_squadra, prestiti_in=prestiti_in, prestiti_out=prestiti_out, slot_giocatori=slot_giocatori)






def richiedi_terminazione_prestito(conn, id_prestito, nome_squadra):
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Prima controllo che l'altra squadra non abbia già effettuato una richiesta di terminazione
        cur.execute('''
                    SELECT stato
                    FROM prestito
                    WHERE id = %s;
        ''', (id_prestito,))
        stato_prestito = cur.fetchone()

        if stato_prestito and stato_prestito['stato'] == 'richiesta_di_terminazione':
            flash("❌ L'altra squadra ha già richiesto una terminazione anticipata per questo giocatore. Aggiornare la pagina", "danger")
            return              # Il finally viene eseguito comunque

        # Se lo stato è 'in_corso' allora cambialo in 'richiesta_di_terminazione'
        cur.execute('''
                    UPDATE prestito
                    SET stato = 'richiesta_di_terminazione',
                        richiedente_terminazione = %s
                    WHERE id = %s;
        ''', (nome_squadra, id_prestito))
        conn.commit()
        flash("✅ Richiesta di terminazione anticipata inviata con successo.", "success")
        telegram_utils.richiesta_terminazione_prestito(conn, id_prestito)



    except Exception as e:
        print(f"Errore: {e}")
        flash("❌ Errore nel controllo del prestito, riprovare.", "danger")

    finally:
        release_connection(None, cur)




def accetta_terminazione(conn, id_prestito):

    rome_tz = pytz.timezone("Europe/Rome")
    print(id_prestito)
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Controllo che il prestito non sia terminato mentre la pagina era aperta
        cur.execute('''
                    SELECT data_fine
                    FROM prestito
                    WHERE id = %s;
        ''', (id_prestito,))
        row = cur.fetchone()

        if row is None:
            flash("❌ Prestito non trovato.", "danger")
            return

        data_fine = row['data_fine']

        now = datetime.now(rome_tz)

        if data_fine and data_fine < now:
            flash("Il prestito è già terminato.", "warning")
            return

        # Modifico lo stato del prestito e imposto la data di fine prestito
        cur.execute('''
                    UPDATE prestito
                    SET stato = 'terminato',
                        richiedente_terminazione = NULL,
                        data_fine = (NOW() AT TIME ZONE 'Europe/Rome')
                    WHERE id = %s;
        ''', (id_prestito,))

        # Prima di modificare le imformazioni sul giocatore coinvolto, recupero le info sulle squadre coinvolte nel prestito
        cur.execute('''
                    SELECT giocatore, squadra_prestante
                    FROM prestito
                    WHERE id = %s; 
        ''', (id_prestito,))
        row = cur.fetchone()
        
        # Modifico le info sul giocatore
        cur.execute('''
                    UPDATE giocatore
                    SET squadra_att = %s,
                        tipo_contratto = 'Indeterminato'
                    WHERE id = %s;
        ''', (row['squadra_prestante'], row['giocatore']))

        conn.commit()
        flash("✅ Prestito terminato con successo.", "success")
        telegram_utils.richiesta_terminazione_prestito_risposta(conn, id_prestito, "Accettato")



    except Exception as e:
        print(f"Errore: {e}")
        flash("❌ Si è verificato un errore. Ricaricare la pagina.", "danger")

    finally:
        release_connection(None, cur)






def rifiuta_terminazione(conn, id_prestito):

    rome_tz = pytz.timezone("Europe/Rome")
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Controllo che il prestito non sia terminato mentre la pagina era aperta
        cur.execute('''
                    SELECT data_fine
                    FROM prestito
                    WHERE id = %s;
        ''', (id_prestito,))
        row = cur.fetchone()

        if row is None:
            flash("❌ Prestito non trovato.", "danger")
            return

        data_fine = row['data_fine']

        now = datetime.now(rome_tz)

        if data_fine and data_fine < now:
            flash("Il prestito è già terminato.", "warning")
            return
        

        # Rimetto il prestito nel suo stato 'in_corso'
        cur.execute('''
                    UPDATE prestito
                    SET stato = 'in_corso',
                        richiedente_terminazione = NULL
                    WHERE id = %s;
        ''', (id_prestito,))
        conn.commit()

        flash("✅ Richiesta di terminazione anticipata rifiutata con successo.", "success")
        telegram_utils.richiesta_terminazione_prestito_risposta(conn, id_prestito, "Rifiutato")


    except Exception as e:
        print(f"Errore: {e}")
        flash("❌ Si è verificato un errore. Ricaricare la pagina.", "danger")

    finally:
        release_connection(None, cur)
