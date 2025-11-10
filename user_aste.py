import psycopg2
import datetime
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from db import get_connection, release_connection
from user import format_partecipanti, formatta_data
from queries import get_crediti_squadra, get_offerta_totale


aste_bp = Blueprint('aste', __name__, url_prefix='/aste')



# Pagina gestione aste utente
@aste_bp.route("/aste/<nome_squadra>", methods=["GET", "POST"])
def user_aste(nome_squadra):

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # BOTTONE ISCRIVITI
            asta_id = request.form.get("asta_id_aste_a_cui_iscriversi")
            if asta_id:

                tempo_scaduto = False
                cur.execute('''
                            SELECT stato
                            FROM asta
                            WHERE id = %s;
                ''', (asta_id,))
                stato = cur.fetchone()['stato']

                if stato == 'in_corso':
                    tempo_scaduto = True
                    flash("Iscrizione fallita, tempo scaduto.", "danger")

                
                if tempo_scaduto == False:
                    # Controllo se l'utente loggato è già iscritto all'asta, a volte capita che un utente possa iscriversi due volte.
                    cur.execute('''
                                SELECT %s = ANY(partecipanti) AS gia_iscritto
                                FROM asta
                                WHERE id = %s;
                    ''', (nome_squadra, asta_id))
                    gia_iscritto = cur.fetchone()["gia_iscritto"]
                
                    # Se non gia iscritto, iscriviti
                    if not gia_iscritto:
                        cur.execute('''
                                    UPDATE asta
                                    SET partecipanti = array_append(partecipanti, %s)
                                    WHERE id = %s;
                        ''', (nome_squadra, asta_id))
                        conn.commit()

                        # Recupero info id giocatore dell'asta
                        cur.execute('''
                                    SELECT giocatore 
                                    FROM asta 
                                    WHERE id = %s;
                        ''', (asta_id))
                        id_giocatore = cur.fetchone()['giocatore']

                        # Recupero info sul nome del giocatore
                        cur.execute('''
                                    SELECT nome
                                    FROM giocatore
                                    WHERE id = %s;
                        ''', (id_giocatore,))
                        nome_giocatore = cur.fetchone()['nome']

                        flash(f"Ti sei iscritto all'asta per { nome_giocatore }.", "success")
                        return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))
            

            
        # Lista aste, tutte insieme
        aste = []
        cur.execute('''
                    SELECT a.id, g.nome, a.squadra_vincente, a.ultima_offerta, a.tempo_fine_asta, a.tempo_fine_mostra_interesse, a.stato, a.partecipanti
                    FROM asta a
                    JOIN giocatore g ON a.giocatore = g.id
                    WHERE (a.stato = 'in_corso' AND %s = ANY(a.partecipanti)) 
                    OR a.stato = 'mostra_interesse'
                    OR (a.stato = 'conclusa' AND a.squadra_vincente = %s);
        ''', (nome_squadra, nome_squadra))
        aste_raw = cur.fetchall()

        for a in aste_raw:

            data_scadenza = formatta_data(a["tempo_fine_asta"])
            tempo_fine_mostra_interesse = formatta_data(a["tempo_fine_mostra_interesse"])

            gia_iscritto_all_asta = False
            if nome_squadra in a["partecipanti"]:
                gia_iscritto_all_asta = True
            
            partecipanti = format_partecipanti(a["partecipanti"])

            aste.append({
                "asta_id": a["id"],
                "giocatore": a["nome"],
                "squadra_vincente": a["squadra_vincente"],
                "ultima_offerta": a["ultima_offerta"],
                "tempo_fine_mostra_interesse": tempo_fine_mostra_interesse,
                "data_scadenza": data_scadenza,
                "stato": a["stato"],
                "partecipanti": partecipanti,
                "gia_iscritto_all_asta": gia_iscritto_all_asta
            })

        

        # Ottengo i crediti e i crediti disponibili
        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        offerta_massima_possibile = crediti - offerta_totale

        block_button = False
        if crediti == 0 or offerta_massima_possibile == 0:
            block_button = True

    except Exception as e:
        print("Errore", e)
        flash("Errore durante il caricamento delle aste.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_aste.html", nome_squadra=nome_squadra, aste=aste, block_button=block_button, crediti=crediti, crediti_effettivi=offerta_massima_possibile)










# Creazione nuova asta
@aste_bp.route("/nuova_asta/<nome_squadra>", methods=["GET", "POST"])
def nuova_asta(nome_squadra):
    conn = None
    giocatori_disponibili_per_asta = []

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupera i giocatori disponibili per l'asta
        cur.execute('''
            SELECT nome
            FROM giocatore AS g
            WHERE tipo_contratto = 'Svincolato'
              AND priorita = 1
              AND NOT EXISTS (
                    SELECT 1 
                    FROM asta a 
                    WHERE a.giocatore = g.id 
                        AND a.stato IN ('mostra_interesse', 'in_corso')
              )
        ''')
        giocatori_disponibili_per_asta = [row["nome"] for row in cur.fetchall()]

        if request.method == "POST":
            giocatore_scelto = request.form.get("giocatore", "").strip()
            if giocatore_scelto not in giocatori_disponibili_per_asta:
                flash("Giocatore non valido o già in un'asta.", "danger")
                return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))

            try:
                # Locka il giocatore per evitare race condition
                cur.execute('''
                            SELECT id 
                            FROM giocatore 
                            WHERE nome = %s FOR UPDATE;
                ''', (giocatore_scelto,))
                giocatore_raw = cur.fetchone()

                if not giocatore_raw:
                    flash("Giocatore non trovato nel database.", "danger")
                    return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))

                giocatore_id = giocatore_raw["id"]

                # Inserisci l'asta
                cur.execute('''
                    INSERT INTO asta (
                        giocatore, squadra_vincente, ultima_offerta,
                        tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti, gia_elaborata
                    )
                    VALUES (%s, %s, NULL, NULL, (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day', 'mostra_interesse', %s, FALSE)
                ''', (giocatore_id, nome_squadra, [nome_squadra]))
                conn.commit()

                flash(f"Asta per {giocatore_scelto} creata con successo!", "success")
                return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))

            except psycopg2.errors.SerializationFailure:
                conn.rollback()
                flash("Un altro utente ha appena creato un'asta per questo giocatore. Riprova.", "warning")
                return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))

    except Exception as e:
        print("Errore nuova_asta:", e)
        flash(f"Errore nella creazione dell'asta: {e}", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_nuova_asta.html", giocatori_disponibili_per_asta=giocatori_disponibili_per_asta)





@aste_bp.route("/singola_asta_attiva/<int:asta_id>/<nome_squadra>", methods=["GET", "POST"])
def singola_asta_attiva(asta_id, nome_squadra):
    asta = None

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Bottone RINUNCIA
            asta_id_rinuncia = request.form.get("bottone_rinuncia")
            if asta_id_rinuncia:
                cur.execute('''
                            UPDATE asta
                            SET partecipanti = array_remove(partecipanti, %s)
                            WHERE id = %s;
                ''', (nome_squadra, asta_id_rinuncia))
                conn.commit()
                flash("Hai rinunciato all'asta.", "success")
                return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))

            # Bottone RILANCIA OFFERTA
            nuova_offerta = request.form.get("bottone_rilancia")
            if nuova_offerta:
                # Blocca la riga dell'asta per aggiornamenti concorrenti
                cur.execute('''
                            SELECT ultima_offerta, squadra_vincente 
                            FROM asta 
                            WHERE id = %s FOR UPDATE;
                ''', (asta_id,))
                asta_dati = cur.fetchone()

                # Controllo sui valori dell'asta prima di rilanciare
                if asta_dati['ultima_offerta'] < int(nuova_offerta) and asta_dati['squadra_vincente']:
                    cur.execute('''
                        UPDATE asta
                        SET ultima_offerta = %s,
                            squadra_vincente = %s,
                            tempo_fine_asta = (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day'
                        WHERE id = %s;
                    ''', (nuova_offerta, nome_squadra, asta_id))
                    conn.commit()
                    flash(f"Hai rilanciato l'offerta a {nuova_offerta}.", "success")
                    return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))
                
                flash("Attenzione, valori non aggiornati, verrai reindirizzato alla pagina aggiornata.", "danger")
                return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))

        # Recupero dati asta
        cur.execute('''
            WITH giocatori_svincolati AS (
                SELECT id, nome
                FROM giocatore
                WHERE tipo_contratto = 'Svincolato'
            )
            SELECT g.nome, a.ultima_offerta, a.squadra_vincente, a.tempo_fine_asta, a.partecipanti
            FROM asta a
            JOIN giocatori_svincolati g ON a.giocatore = g.id
            WHERE a.id = %s;
        ''', (asta_id,))
        asta_raw = cur.fetchone()

        if asta_raw:
            # Recupero crediti disponibili
            crediti = get_crediti_squadra(conn, nome_squadra)
            offerta_totale = get_offerta_totale(conn, nome_squadra)
            

            # Calcolo offerta massima possibile
            if asta_raw["squadra_vincente"] == nome_squadra:
                offerta_massima_possibile = crediti - (offerta_totale - (asta_raw["ultima_offerta"] or 0))
            else:
                offerta_massima_possibile = crediti - offerta_totale

            partecipanti = format_partecipanti(asta_raw["partecipanti"])
            data_scadenza = asta_raw["tempo_fine_asta"]
            if isinstance(data_scadenza, str):
                data_scadenza = datetime.fromisoformat(data_scadenza.split(".")[0])
            data_scadenza_str = data_scadenza.strftime("%d/%m/%Y %H:%M")

            asta = {
                "id": asta_id,
                "giocatore": asta_raw["nome"],
                "ultima_offerta": asta_raw["ultima_offerta"],
                "squadra_vincente": asta_raw["squadra_vincente"],
                "tempo_fine_asta": data_scadenza_str,
                "partecipanti": partecipanti,
                "offerta_massima_possibile": offerta_massima_possibile
            }
        else:
            flash("Asta non trovata.", "warning")

    except Exception as e:
        print("Errore:", e)
        flash("Errore durante il caricamento dell'asta.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("singola_asta_attiva.html", asta=asta, nome_squadra=nome_squadra)

