import psycopg2
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import get_connection, release_connection
from queries import get_crediti_squadra, get_offerta_totale, get_slot_occupati, get_quotazione_attuale
from psycopg2 import extensions
from psycopg2.extras import RealDictCursor
from datetime import datetime, time
import math

user_bp = Blueprint('user', __name__, url_prefix='/user')

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadraLogin/<nome_squadra>")
def squadraLogin(nome_squadra):
    return render_template("squadraLogin.html", nome_squadra=nome_squadra)


# Pagina gestione aste utente
@user_bp.route("/aste/<nome_squadra>", methods=["GET", "POST"])
def user_aste(nome_squadra):

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # BOTTONE ISCRIVITI
            asta_id = request.form.get("asta_id_aste_a_cui_iscriversi")
            if asta_id:

                # Controllo se l'utente loggato è già iscritto all'asta, a volte capita che un utente possa iscriversi due volte.
                cur.execute('''SELECT %s = ANY(partecipanti) AS gia_iscritto
                            FROM asta
                            WHERE id = %s;''', (nome_squadra, asta_id))
                gia_iscritto = cur.fetchone()["gia_iscritto"]
                
                # Se non gia iscritto, iscriviti
                if not gia_iscritto:
                    cur.execute('''UPDATE asta
                            SET partecipanti = array_append(partecipanti, %s)
                            WHERE id = %s;''', (nome_squadra, asta_id))
                    conn.commit()

                    # Recupero info giocatore dell'asta
                    cur.execute("SELECT giocatore FROM asta WHERE id = %s;", (asta_id))
                    nome_giocatore = cur.fetchone()['giocatore']
                    flash(f"Ti sei iscritto all'asta per { nome_giocatore }.", "success")
                    return redirect(url_for("user.user_aste", nome_squadra=nome_squadra))
            

            
        # Lista aste, tutte insieme
        aste = []
        cur.execute('''WITH giocatori_svincolati AS (
                    SELECT id, nome
                    FROM giocatore
                    WHERE tipo_contratto = 'Svincolato')
                    
                    SELECT a.id, g.nome, a.squadra_vincente, a.ultima_offerta, a.tempo_fine_asta, a.tempo_fine_mostra_interesse, a.stato, a.partecipanti
                    FROM asta a
                    JOIN giocatori_svincolati g ON a.giocatore = g.id
                    WHERE (a.stato = 'in_corso' AND %s = ANY(a.partecipanti)) 
                    OR a.stato = 'mostra_interesse'
                    OR (a.stato = 'conclusa' AND a.squadra_vincente = %s);''', (nome_squadra, nome_squadra))
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
@user_bp.route("/nuova_asta/<nome_squadra>", methods=["GET", "POST"])
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
                  SELECT 1 FROM asta a 
                  WHERE a.giocatore = g.id 
                    AND a.stato IN ('mostra_interesse', 'in_corso')
              )
        ''')
        giocatori_disponibili_per_asta = [row["nome"] for row in cur.fetchall()]

        if request.method == "POST":
            giocatore_scelto = request.form.get("giocatore", "").strip()
            if giocatore_scelto not in giocatori_disponibili_per_asta:
                flash("Giocatore non valido o già in un'asta.", "danger")
                return redirect(url_for("user.nuova_asta", nome_squadra=nome_squadra))

            try:
                # Locka il giocatore per evitare race condition
                cur.execute('SELECT id FROM giocatore WHERE nome = %s FOR UPDATE', (giocatore_scelto,))
                row = cur.fetchone()
                if not row:
                    flash("Giocatore non trovato nel database.", "danger")
                    return redirect(url_for("user.nuova_asta", nome_squadra=nome_squadra))

                giocatore_id = row["id"]

                # Inserisci l'asta
                cur.execute('''
                    INSERT INTO asta (
                        giocatore, squadra_vincente, ultima_offerta,
                        tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti
                    )
                    VALUES (%s, %s, NULL, NULL, (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day', 'mostra_interesse', %s)
                ''', (giocatore_id, nome_squadra, [nome_squadra]))
                conn.commit()

                flash(f"Asta per {giocatore_scelto} creata con successo!", "success")
                return redirect(url_for("user.user_aste", nome_squadra=nome_squadra))

            except psycopg2.errors.SerializationFailure:
                conn.rollback()
                flash("Un altro utente ha appena creato un'asta per questo giocatore. Riprova.", "warning")
                return redirect(url_for("user.nuova_asta", nome_squadra=nome_squadra))

        cur.close()

    except Exception as e:
        print("Errore nuova_asta:", e)
        flash(f"Errore nella creazione dell'asta: {e}", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_nuova_asta.html", giocatori_disponibili_per_asta=giocatori_disponibili_per_asta)





@user_bp.route("/singola_asta_attiva/<int:asta_id>/<nome_squadra>", methods=["GET", "POST"])
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
                return redirect(url_for("user.user_aste", nome_squadra=nome_squadra))

            # Bottone RILANCIA OFFERTA
            nuova_offerta = request.form.get("bottone_rilancia")
            if nuova_offerta:
                # Blocca la riga dell'asta per aggiornamenti concorrenti
                cur.execute('SELECT ultima_offerta, squadra_vincente FROM asta WHERE id = %s FOR UPDATE', (asta_id,))
                asta_dati = cur.fetchone()

                if asta_dati:
                    cur.execute('''
                        UPDATE asta
                        SET ultima_offerta = %s,
                            squadra_vincente = %s,
                            tempo_fine_asta = (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day'
                        WHERE id = %s;
                    ''', (nuova_offerta, nome_squadra, asta_id))
                    conn.commit()
                    flash(f"Hai rilanciato l'offerta a {nuova_offerta}.", "success")
                    return redirect(url_for("user.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))

        # --- Recupero dati asta ---
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




@user_bp.route("/mercato/<nome_squadra>", methods=["GET", "POST"])
def user_mercato(nome_squadra):

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Bottone ANNULLA scambio
            scambio_id = request.form.get("annulla_scambio")
            if scambio_id:
                cur.execute('''UPDATE scambio
                            SET stato = 'annullato' 
                            WHERE id = %s;''', (scambio_id,))
                conn.commit()


            # Bottone ACCETTA scambio
            scambio_id = request.form.get("accetta_scambio")
            if scambio_id:
                effettua_scambio(scambio_id)

            
            # Bottone RIFIUTA scambio
            scambio_id = request.form.get("rifiuta_scambio")
            if scambio_id:
                cur.execute('''UPDATE scambio
                            SET stato= 'rifiutato',
                                data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                            WHERE id = %s; ''', (scambio_id,))
                conn.commit()




        
        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        offerta_massima_possibile = crediti - offerta_totale

        scambi_raw = []
        scambi = []

        cur.execute('''SELECT *
                    FROM scambio
                    WHERE squadra_proponente = %s
                    OR squadra_destinataria = %s;''', (nome_squadra, nome_squadra))
        scambi_raw = cur.fetchall()

        for s in scambi_raw:
            scambi.append({
                "scambio_id": s["id"],
                "squadra_proponente": s["squadra_proponente"],
                "squadra_destinataria": s["squadra_destinataria"],
                "giocatori_offerti": format_giocatori(s["giocatori_offerti"]),
                "giocatori_richiesti": format_giocatori(s["giocatori_richiesti"]),
                "crediti_offerti": s["crediti_offerti"],
                "crediti_richiesti": s["crediti_richiesti"],
                "messaggio": s["messaggio"],
                "stato": s["stato"],
                "data_proposta": formatta_data(s["data_proposta"]),
                "data_risposta": formatta_data(s["data_risposta"]),
            })
        
    except Exception as e:
        print("Errore:", e)
        flash("Errore durante il caricamento degli scambi.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_mercato.html", nome_squadra=nome_squadra, crediti=crediti, offerta_massima_possibile=offerta_massima_possibile, scambi=scambi)




@user_bp.route("/nuovo_scambio/<nome_squadra>", methods=["GET", "POST"])
def nuovo_scambio(nome_squadra):
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        
        if request.method == "POST":
            squadra_destinataria = request.form.get("squadra_destinataria")
            crediti_offerti = int(request.form.get("crediti_offerti", 0))
            crediti_richiesti = int(request.form.get("crediti_richiesti", 0))
            giocatori_offerti = [int(g) for g in request.form.getlist("giocatori_offerti")]
            giocatori_richiesti = [int(g) for g in request.form.getlist("giocatori_richiesti")]
            messaggio = request.form.get("messaggio", "").strip()

            if not squadra_destinataria:
                flash("Seleziona una squadra destinataria.", "warning")
                return redirect(nuovo_scambio(nome_squadra))
            
            if not giocatori_offerti and crediti_offerti == 0:
                flash("Devi offrire almeno un giocatore o dei crediti.", "warning")
                return redirect(nuovo_scambio(nome_squadra))
            
            if not giocatori_richiesti and crediti_richiesti == 0:
                flash("Devi richiedere almeno un giocatore o dei crediti.", "warning")
                return redirect(request.url)
            

            # Inserimento nuova proposta di scambio
            cur.execute('''INSERT INTO scambio (
                        squadra_proponente, squadra_destinataria, crediti_offerti, crediti_richiesti, giocatori_offerti, giocatori_richiesti, messaggio, stato, data_proposta)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome')
                        RETURNING id;''', (
                            nome_squadra,
                            squadra_destinataria,
                            crediti_offerti,
                            crediti_richiesti,
                            giocatori_offerti,
                            giocatori_richiesti,
                            messaggio,
                            'in_attesa'
                        ))
            
            conn.commit()
            flash("✅ Proposta di scambio inviata con successo!", "success")
            return redirect(url_for("user.user_mercato", nome_squadra=nome_squadra))




        # Recupero tutte le squadre
        cur.execute("SELECT nome, crediti FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome;")
        squadre_raw = cur.fetchall()
        squadre = []
        crediti_effettivi = 0

        for s in squadre_raw:

            offerta_totale = get_offerta_totale(conn, nome_squadra)
            offerta_massima_possibile = s["crediti"] - offerta_totale

            squadre.append({
                "nome": s["nome"],
                "offerta_massima_possibile": offerta_massima_possibile
            })

            if s["nome"] == nome_squadra:
                crediti_effettivi = offerta_massima_possibile
        

        # Recupero tutti i giocatori validi (non svincolati, non in prestito, non in hold)
        cur.execute("""
            SELECT id, nome, squadra_att
            FROM giocatore
            WHERE squadra_att IS NOT NULL
              AND squadra_att != 'Svincolati'
              AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold')
            ORDER BY squadra_att, nome;""")
        giocatori_raw = cur.fetchall()

        # Filtra i giocatori appartenenti alla squadra loggata
        miei_giocatori = [g for g in giocatori_raw if g["squadra_att"] == nome_squadra]

         # Trasformo la lista di giocatori in dizionari puliti per JSON
        giocatori = [{"id": g["id"], "nome": g["nome"], "squadra_att": g["squadra_att"]} for g in giocatori_raw]

        return render_template(
            "user_nuovo_scambio.html", nome_squadra=nome_squadra, squadre=squadre, giocatori=giocatori, miei_giocatori=miei_giocatori, crediti_effettivi=crediti_effettivi)

    except Exception as e:
        print(f"❌ Errore durante il caricamento della pagina 'nuovo scambio': {e}")
        flash("Si è verificato un errore nel caricamento della pagina.", "danger")
        return render_template("user_mercato.html", nome_squadra=nome_squadra)

    finally:
        release_connection(conn, cur)



def effettua_scambio(id):
    
    try:
        conn = get_connection()
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupero dati dello scambio
        cur.execute('''SELECT *
                    FROM scambio
                    WHERE id = %s
                    AND stato = 'in_attesa'
                    FOR UPDATE;''', (id,))
        scambio = cur.fetchone()

        if not scambio:
            raise ValueError(f"Nessuno scambio valido trovato con id:", id)
        
        squadra_proponente = scambio["squadra_proponente"]
        squadra_destinataria = scambio["squadra_destinataria"]
        crediti_offerti = scambio["crediti_offerti"] or 0
        crediti_richiesti = scambio["crediti_richiesti"] or 0
        giocatori_offerti = scambio["giocatori_offerti"] or []
        giocatori_richiesti = scambio["giocatori_richiesti"] or []


        # Controllo che le squadre abbiano abbastanza crediti per effettuare lo scambio
        cur.execute("SELECT crediti FROM squadra WHERE nome = %s FOR UPDATE;", (squadra_proponente,))
        crediti_prop = cur.fetchone()["crediti"]
        
        offerta_tot_prop = get_offerta_totale(conn, squadra_proponente)
        crediti_disp_prop = crediti_prop - offerta_tot_prop
        

        cur.execute("SELECT crediti FROM squadra WHERE nome = %s FOR UPDATE;", (squadra_destinataria,))
        crediti_dest = cur.fetchone()["crediti"]
        
        offerta_tot_dest = get_offerta_totale(conn, squadra_destinataria)
        crediti_disp_dest = crediti_dest - offerta_tot_dest

        if crediti_disp_prop < crediti_offerti:
            raise ValueError(f"La squadra {squadra_proponente} non ha abbastanza crediti ({crediti_disp_prop}).")
        if crediti_disp_dest < crediti_richiesti:
            raise ValueError(f"La squadra {squadra_destinataria} non ha abbastanza crediti ({crediti_disp_dest}).")
        
        # Controllo che le squadre abbiano abbastanza slot giocatori disponibili per effettuare gli scambi
        slot_squadra_proponente = get_slot_occupati(conn, squadra_proponente)
        num_giocatori_in_entrata = len(giocatori_richiesti)
        if slot_squadra_proponente + num_giocatori_in_entrata > 32:
            raise ValueError(f"La squadra {squadra_proponente} non ha abbastanza slot giocatori liberi.")
        

        slot_squadra_destinataria = get_slot_occupati(conn, squadra_destinataria)
        num_giocatori_in_uscita = len(giocatori_offerti)
        if slot_squadra_destinataria + num_giocatori_in_uscita > 32:
            raise ValueError(f"La squadra {squadra_destinataria} non ha abbastanza slot giocatori liberi.")
        

        # Eseguo il trasferimento dei giocatori
        for giocatore_id in giocatori_offerti:
            cur.execute('''UPDATE giocatore
                        SET detentore_cartellino = %s
                        WHERE id = %s;''', (squadra_destinataria, giocatore_id))
            
        for giocatore_id in giocatori_richiesti:
            cur.execute('''UPDATE giocatore
                        SET detentore_cartellino = %s
                        WHERE id = %s;''', (squadra_proponente, giocatore_id))
            
        
        # Aggiorno i crediti delle due squadre
        cur.execute('''UPDATE squadra
                    SET crediti = crediti - %s + %s
                    WHERE nome = %s;''', (crediti_offerti, crediti_richiesti, squadra_proponente))
        
        cur.execute('''UPDATE squadra
                    SET crediti = crediti - %s + %s
                    WHERE nome = %s;''', (crediti_richiesti, crediti_offerti, squadra_destinataria))
        
        
        # Aggiorno lo stato dello scambio
        cur.execute('''UPDATE scambio
                    SET stato = 'accettato',
                    data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                    WHERE id = %s;''', (id,))
        
        conn.commit()
        print(f"✅ Scambio completato con successo tra {squadra_proponente} e {squadra_destinataria}")
        return True
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ Errore durante l'esecuzione dello scambio: {e}")
        return False
    
    finally:
        release_connection(conn, cur)




@user_bp.route("/prestiti/<nome_squadra>", methods=["GET", "POST"])
def user_prestiti(nome_squadra):

    conn = None
    cur = None

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Bottone ANNULLA prestito
            id_prestito_da_annullare = request.form.get("annulla_prestito")
            if id_prestito_da_annullare:
                cur.execute('''UPDATE prestito
                            SET stato = 'annullato'
                            WHERE id = %s;''', (id_prestito_da_annullare))
                conn.commit()
                flash("Annullata con successo la richiesta di prestito", "success")


            # Bottone ACCETTA prestito
            id_prestito_da_accettare = request.form.get("accetta_prestito")
            if id_prestito_da_accettare:
                attiva_prestito(id_prestito_da_accettare, nome_squadra)

            
            # Bottone RIFIUTA prestito
            id_prestito_da_rifiutare = request.form.get("rifiuta_prestito")
            if id_prestito_da_rifiutare:
                cur.execute('''UPDATE prestito
                            SET stato = 'rifiutato'
                            WHERE id = %s;''', (id_prestito_da_rifiutare,))
                conn.commit()
                flash("Prestito rifiutato con successo.", "success")




        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        crediti_disponibili = crediti - offerta_totale


        cur.execute('''SELECT *
                    FROM prestito
                    WHERE (squadra_prestante = %s
                    OR squadra_ricevente = %s)
                    AND stato = 'in_attesa';''', (nome_squadra, nome_squadra))
        prestiti_raw = cur.fetchall()

        prestiti = []
        for p in prestiti_raw:
            prestiti.append({
                "prestito_id": p["id"],
                "giocatore": format_giocatori(p["giocatore"]),
                "squadra_prestante": p["squadra_prestante"],
                "squadra_ricevente": p["squadra_ricevente"],
                "stato": p["stato"],
                "data_inizio": formatta_data(p["data_inizio"]),
                "data_fine": formatta_data(p["data_fine"])
            })


    except Exception as e:
        print(f"❌ Errore durante il caricamento della pagina 'prestiti': {e}")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra)
    
    finally:
        release_connection(conn, cur)

    return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=crediti, crediti_disponibili=crediti_disponibili, prestiti=prestiti)





@user_bp.route("/nuovo_prestito/<nome_squadra>", methods=["GET", "POST"])
def nuovo_prestito(nome_squadra):

    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            squadra_prestante = request.form.get("squadra_prestante")
            giocatore_richiesto = request.form.get("giocatore_richiesto")
            data_fine = request.form.get("data_fine")
            messaggio = request.form.get("messaggio", "").strip()

            if not squadra_prestante or not giocatore_richiesto or not data_fine:
                flash("Errore: seleziona una squadra, un giocatore e una data di fine prestito.", "danger")
                return redirect(url_for("user.nuovo_prestito", nome_squadra=nome_squadra))
            
            data_fine = datetime.strptime(data_fine, "%Y-%m-%d")
            data_fine = datetime.combine(data_fine.date(), time(hour=12, minute=0, second=0))

            cur.execute('''INSERT INTO prestito (
                        giocatore, squadra_prestante, squadra_ricevente, stato, data_inizio, data_fine)
                        VALUES(%s, %s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome', %s)
                        RETURNING id; ''', (giocatore_richiesto, squadra_prestante, nome_squadra, 'in_attesa', data_fine))
            conn.commit()
            flash("Richiesta inviata correttamente!", "success")
            redirect(url_for("user.user_prestiti", nome_squadra=nome_squadra))
            


        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        crediti_disponibili = crediti - offerta_totale

        # Selezione dei giocatori
        cur.execute('''SELECT id, nome, squadra_att
                    FROM giocatore g
                    WHERE g.tipo_contratto <> 'Fanta-Prestito'
                    AND g.squadra_att <> 'Svincolato'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM prestito p
                        WHERE p.giocatore = g.id
                        AND p.stato = 'in_attesa'
                        AND p.squadra_ricevente = %s);''', (nome_squadra,))
        giocatori_raw = cur.fetchall()

        giocatori = []
        for g in giocatori_raw:
            giocatori.append({
                "id": g["id"],
                "nome": g["nome"],
                "squadra_att": g["squadra_att"]
            })

        # Selezione dei nomi delle squadre, tranne la squadra loggata e Svincolato
        cur.execute('''SELECT nome
                    FROM squadra
                    WHERE nome <> %s
                    AND nome <> 'Svincolato';''', (nome_squadra,))
        squadre_raw = cur.fetchall()

        squadre = []
        for s in squadre_raw:
            squadre.append({
                "nome": s["nome"]
            })

    except Exception as e:
        print(f"❌ Errore durante il caricamento della pagina 'nuovo_prestito': {e}")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra)
    
    finally:
        release_connection(conn, cur)

    return render_template("user_nuovo_prestito.html", nome_squadra=nome_squadra, crediti=crediti, crediti_disponibili=crediti_disponibili, giocatori=giocatori, squadre=squadre)





def attiva_prestito(id_prestito_da_attivare, nome_squadra):

    if not id_prestito_da_attivare:
        flash("❌ Prestito non trovato.", "danger")
        return redirect(url_for("user.user_prestiti", nome_squadra=nome_squadra))
    
    conn = None
    cur = None
    try:
        conn = get_connection()
        conn.autocommit = False
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupero info prestito
        cur.execute('''SELECT *
                    FROM prestito
                    WHERE id = %s;''', (id_prestito_da_attivare,))
        prestito = cur.fetchone()

        # Cambio di stato
        cur.execute('''UPDATE prestito
                    SET stato = 'in_corso'
                    WHERE id = %s;''', (id_prestito_da_attivare,))
        
        # Modifica info giocatore
        cur.execute('''UPDATE giocatore
                    SET squadra_att = %s,
                    tipo_contratto = 'Fanta-Prestito'
                    WHERE id = %s;''', (prestito['squadra_ricevente'], prestito['giocatore']))
        
        # Cancellare altri prestiti per lo stesso giocatore fatti da altre squadre
        cur.execute('''UPDATE prestito
                    SET stato = 'rifiutato'
                    WHERE squadra_prestante = %s
                    AND giocatore = %s
                    AND stato = 'in_attesa';''', (prestito['squadra_prestante'], prestito['giocatore']))

        conn.commit()
        flash("✅ Prestito avviato correttamente.", "success")


    except Exception as e:
        print(f"❌ Errore durante l'attivazione del prestito: {e}")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra)
    
    finally:
        release_connection(conn, cur)










@user_bp.route("/gestione_rosa/<nome_squadra>")
def user_gestione_rosa(nome_squadra):
    return render_template("user_gestione_rosa.html", nome_squadra=nome_squadra)


@user_bp.route("/user_primavera/<nome_squadra>", methods=["GET", "POST"])
def user_primavera(nome_squadra):

    conn = None
    cur = None
    primavera = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            id_giocatore_da_promuovere = request.form.get("id_giocatore_da_promuovere")
            if id_giocatore_da_promuovere:
                cur.execute('''UPDATE giocatore
                            SET tipo_contratto = 'Indeterminato'
                            WHERE id = %s;''', (id_giocatore_da_promuovere,))
                conn.commit()
                flash("✅ Giocatore promosso in prima squadra con successo.", "success")


        # Selezione dei giocatori in primavera
        cur.execute('''SELECT id, nome, ruolo, quot_att_mantra
                    FROM giocatore
                    WHERE squadra_att = %s
                    AND tipo_contratto = 'Primavera';''', (nome_squadra,))
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
        print(f"❌ Errore durante il caricamento della primavera.")
        flash("Errore durante il caricamento della primavera.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("user_primavera.html", nome_squadra=nome_squadra, primavera=primavera)





@user_bp.route("/user_tagli/<nome_squadra>", methods=["GET", "POST"])
def user_tagli(nome_squadra):

    conn = None
    cur = None
    rosa = []

    try:
        conn = get_connection()
        conn.autocommit = False
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
                    return redirect(url_for("user.user_tagli", nome_squadra=nome_squadra))

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

                conn.commit()
                flash(f"✅ Giocatore tagliato con successo! Costo: {costo_taglio} crediti.", "success")
                return redirect(url_for("user.user_tagli", nome_squadra=nome_squadra))
            




        cur.execute('''
            SELECT id, nome, ruolo, quot_att_mantra
            FROM giocatore
            WHERE squadra_att = %s
              AND tipo_contratto = 'Indeterminato'
            ORDER BY ruolo, nome;''', (nome_squadra,))
        rosa_raw = cur.fetchall()

        for r in rosa_raw:
            ruolo = r['ruolo'].strip("{}")
            rosa.append({
                "id": r['id'],
                "nome": r['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": r["quot_att_mantra"]
            })

    except Exception as e:
        print(f"❌ Errore durante il caricamento o il taglio dei giocatori: {e}")
        flash("Errore durante il caricamento o il taglio dei giocatori.", "danger")
        if conn:
            conn.rollback()

    finally:
        release_connection(conn, cur)

    return render_template(
        "user_tagli.html", nome_squadra=nome_squadra, rosa=rosa, crediti=crediti, crediti_disponibili=crediti_disponibili)



















def format_partecipanti(partecipanti):
    if not partecipanti:
        return ""
    elif len(partecipanti) == 1:
        return partecipanti[0]
    else:
        return ",\n".join(partecipanti)
    


def format_giocatori(giocatori):
    if not giocatori:
        return ""
    
    if isinstance(giocatori, int):
        giocatori = [giocatori]


    nomi = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        for giocatore_id in giocatori:
            cur.execute("""
                SELECT nome
                FROM giocatore
                WHERE id = %s;
            """, (giocatore_id,))
            
            risultato = cur.fetchone()
            if risultato and "nome" in risultato:
                nomi.append(risultato["nome"])
            else:
                nomi.append(f"ID {giocatore_id} (non trovato)")

    except Exception as e:
        print(f"❌ Errore durante il recupero dei nomi giocatori: {e}")
        return "Errore nel recupero dei giocatori"

    finally:
        release_connection(conn, cur)

    # Formattazione pulita dell'output
    if not nomi:
        return ""
    elif len(nomi) == 1:
        return nomi[0]
    else:
        return ", ".join(nomi)



def formatta_data(data_input):

    #Converte una data (stringa o datetime) in formato 'dd/mm/YYYY HH:MM'.
    #Rimuove automaticamente millisecondi e timezone.
    
    if data_input is None:
        return None

    # Se è una stringa ISO, puliscila
    if isinstance(data_input, str):
        # Rimuove millisecondi e timezone se presenti
        data_input = data_input.split("+")[0].split("Z")[0].split(".")[0]
        try:
            data_input = datetime.fromisoformat(data_input)
        except ValueError:
            return data_input  # se non è una data ISO valida, restituisci com'è

    # Se è un oggetto datetime, formatta
    if isinstance(data_input, datetime):
        return data_input.strftime("%d/%m/%Y %H:%M")

    return str(data_input)


