from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

user_bp = Blueprint('user', __name__, url_prefix='/user')

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadraLogin")
def squadraLogin():
    nome_squadra = session.get("nome_squadra")
    return render_template("squadraLogin.html", nome_squadra=nome_squadra)


# Pagina gestione aste utente
@user_bp.route("/aste", methods=["GET", "POST"])
def user_aste():
    nome_squadra = session.get("nome_squadra")


    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # BOTTONE ISCRIVITI
            asta_id = request.form.get("asta_id_aste_a_cui_iscriversi")
            if asta_id:
                cur.execute('''UPDATE asta
                        SET partecipanti = array_append(partecipanti, %s)
                        WHERE id = %s;''', (nome_squadra, asta_id))
                conn.commit()
                flash(f"Ti sei iscritto all'asta: {asta_id}.", "success")
                return redirect(url_for("user.user_aste"))
            
            # BOTTONE RINUNCIA
            asta_id = request.form.get("asta_id_aste_attive")
            if asta_id:
                cur.execute('''UPDATE asta
                        SET partecipanti = array_remove(partecipanti, %s)
                        WHERE id = %s;''', (nome_squadra, asta_id))
                conn.commit()
                flash(f"Hai rinunciato all'asta ID {asta_id}.", "success")
                return redirect(url_for("user.user_aste"))
            




        # ASTE ATTIVE
        aste_attive = []
        cur.execute('''WITH giocatori_svincolati AS (
                SELECT id, nome
                FROM giocatore
                WHERE tipo_contratto = 'Svincolato')

                SELECT a.id, g.nome, a.ultima_offerta, a.squadra_vincente, a.tempo_ultima_offerta, a.partecipanti
                FROM asta a
                JOIN giocatori_svincolati g ON a.giocatore = g.id
                WHERE a.stato = 'in_corso'
                AND %s = ANY(a.partecipanti);''', (nome_squadra,))
        aste_attive_row = cur.fetchall()

        for a in aste_attive_row:
            data_scadenza = a["tempo_ultima_offerta"]

            # Se è una stringa (ad esempio quando viene da Supabase come testo)
            if isinstance(data_scadenza, str):
                data_scadenza = datetime.fromisoformat(data_scadenza.split(".")[0])

            # Aggiungi 24 ore
            data_scadenza += timedelta(hours=24)

            # Ora formatta per la visualizzazione
            data_scadenza_str = data_scadenza.strftime("%d/%m/%Y %H:%M")

            partecipanti = format_partecipanti(a["partecipanti"])

            aste_attive.append({
                "asta_id": a["id"],
                "giocatore": a["nome"],
                "ultima_offerta": a["ultima_offerta"],
                "squadra_vincente": a["squadra_vincente"],
                "data_scadenza": data_scadenza_str,
                "partecipanti": partecipanti
            })


        # ASTE A CUI ISCRIVERSI
        aste_a_cui_iscriversi = []
        cur.execute('''WITH giocatori_svincolati AS (
                        SELECT id, nome
                        FROM giocatore
                        WHERE tipo_contratto = 'Svincolato')
                    
                        SELECT a.id, g.nome, a.tempo_fine_mostra_interesse, a.partecipanti
                        FROM asta a
                        JOIN giocatori_svincolati g ON a.giocatore = g.id
                        WHERE a.stato = 'mostra_interesse';''', (nome_squadra,))
        aste_a_cui_iscriversi_row = cur.fetchall()

    
        for a in aste_a_cui_iscriversi_row:
            data_scadenza = a["tempo_fine_mostra_interesse"]
            if isinstance(data_scadenza, str):
                data_scadenza = datetime.fromisoformat(data_scadenza.split(".")[0])
            data_scadenza += timedelta(hours=24)
            data_scadenza = data_scadenza.strftime("%d/%m/%Y %H:%M")
            gia_iscritto_all_asta = False

            if nome_squadra in a["partecipanti"]:
                gia_iscritto_all_asta = True
            partecipanti = format_partecipanti(a["partecipanti"])

            aste_a_cui_iscriversi.append({
                "asta_id": a["id"],
                "giocatore": a["nome"],
                "data_scadenza": data_scadenza,
                "partecipanti": partecipanti,
                "gia_iscritto_all_asta": gia_iscritto_all_asta
            })


        # ASTE CONCLUSE
        aste_concluse = []
        cur.execute('''SELECT g.nome, a.tempo_fine_asta, a.ultima_offerta, a.squadra_vincente
                    FROM asta a
                    JOIN giocatore g ON a.giocatore = g.id
                    WHERE a.stato = 'conclusa';''')
        aste_concluse_raw = cur.fetchall()

        for a in aste_concluse_raw:
            tempo_fine_asta = a["tempo_fine_asta"]
            if isinstance(tempo_fine_asta, str):
                tempo_fine_asta = datetime.fromisoformat(data_scadenza.split(".")[0])
            data_scadenza = data_scadenza.strftime("%d/%m/%Y %H:%M")

            aste_concluse.append({
                "giocatore": a["nome"],
                "tempo_fine_asta": tempo_fine_asta,
                "ultima_offerta": a["ultima_offerta"],
                "squadra_vincente": a["squadra_vincente"]
            })

    except Exception as e:
        print("Errore", e)
        flash("Errore durante il caricamento delle aste.", "danger")

    finally:
        if conn:
            release_connection(conn)

    return render_template("user_aste.html", nome_squadra=nome_squadra, aste_attive=aste_attive, aste_a_cui_iscriversi=aste_a_cui_iscriversi, aste_concluse=aste_concluse)



# Creazione nuova asta
@user_bp.route("/nuova_asta", methods=["GET", "POST"])
def nuova_asta():
    conn = None
    giocatori_disponibili_per_asta = []  # ✅ inizializzata sempre

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupera i giocatori disponibili per l'asta
        cur.execute('''
            SELECT nome
            FROM giocatore AS g
            WHERE tipo_contratto = 'Svincolato'
              AND NOT EXISTS (
                  SELECT 1 FROM asta a WHERE a.giocatore = g.id
              )
        ''')
        giocatori_disponibili_per_asta = [row["nome"] for row in cur.fetchall()]
        #print(giocatori_disponibili_per_asta)
        if request.method == "POST":
            giocatore_scelto = request.form.get("giocatore", "").strip()
            #print(giocatore_scelto)
            if giocatore_scelto in giocatori_disponibili_per_asta:
                #print("Presente")
                cur.execute('SELECT id FROM giocatore WHERE nome = %s', (giocatore_scelto,))
                row = cur.fetchone()
                print(row)
                if row:
                    giocatore_id = row["id"]
                    nome_squadra = session.get("nome_squadra")
                    cur.execute('''
                        INSERT INTO asta (giocatore, squadra_vincente, ultima_offerta, tempo_ultima_offerta,
                                          tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti)
                        VALUES (%s, %s, NULL, NULL, NULL, NOW() + INTERVAL '1 day' - INTERVAL '22 hours', 'mostra_interesse', %s)
                    ''', (giocatore_id, nome_squadra, [nome_squadra]))
                    conn.commit()

                    flash(f"Asta per {giocatore_scelto} creata con successo!", "success")
                    return redirect(url_for("user.user_aste"))
                else:
                    flash("Giocatore non trovato nel database.", "danger")
            else:
                flash("Giocatore non valido.", "danger")

        cur.close()

    except Exception as e:
        print("Errore nuova_asta:", e)
        flash(f"Errore nella creazione dell'asta: {e}", "danger")

    finally:
        if conn:
            release_connection(conn)

    return render_template("user_nuova_asta.html", giocatori_disponibili_per_asta=giocatori_disponibili_per_asta)




@user_bp.route("/singola_asta_attiva/<int:asta_id>", methods=["GET", "POST"])
def singola_asta_attiva(asta_id):
    nome_squadra = session.get("nome_squadra")
    asta = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # --- RINUNCIA ---
            asta_id_rinuncia = request.form.get("bottone_rinuncia")
            if asta_id_rinuncia:
                cur.execute('''
                    UPDATE asta
                    SET partecipanti = array_remove(partecipanti, %s)
                    WHERE id = %s;
                ''', (nome_squadra, asta_id_rinuncia))
                conn.commit()
                flash("Hai rinunciato all'asta.", "success")
                return redirect(url_for("user.user_aste"))

            # --- RILANCIA OFFERTA ---
            nuova_offerta = request.form.get("bottone_rilancia")
            if nuova_offerta:
                cur.execute('''
                    UPDATE asta
                    SET ultima_offerta = %s,
                        squadra_vincente = %s,
                        tempo_ultima_offerta = NOW()
                    WHERE id = %s;
                ''', (nuova_offerta, nome_squadra, asta_id))
                conn.commit()
                flash(f"Hai rilanciato l'offerta a {nuova_offerta}.", "success")
                return redirect(url_for("user.singola_asta_attiva", asta_id=asta_id))
            
            

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
                "partecipanti": partecipanti
            }
        else:
            flash("Asta non trovata.", "warning")

    except Exception as e:
        print("Errore:", e)
        flash("Errore durante il caricamento dell'asta.", "danger")

    finally:
        if conn:
            release_connection(conn)

    return render_template("singola_asta_attiva.html", asta=asta, nome_squadra=nome_squadra)
























def format_partecipanti(partecipanti):
    if not partecipanti:
        return ""
    elif len(partecipanti) == 1:
        return partecipanti[0]
    else:
        return ",\n".join(partecipanti)


def format_datetime(ts):
    # Converte un timestamp di Supabase in formato 'gg/mm/aaaa' leggibile.
    if not ts:
        return ""
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)  # converte "2025-10-07 13:38:05.44898"
        except ValueError:
            return ts  # se non è formattato bene, restituisci com'è
    return ts.strftime("%d/%m/%Y")  # ✅ giorno/mese/anno

