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


        
    except Exception as e:
        print("Errore", e)
        flash("Errore durante il caricamento delle aste.", "danger")

    finally:
        if conn:
            release_connection(conn)

    return render_template("user_aste.html", nome_squadra=nome_squadra, aste=aste)



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
                        INSERT INTO asta (giocatore, squadra_vincente, ultima_offerta,
                                          tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti)
                        VALUES (%s, %s, NULL, NULL, (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day', 'mostra_interesse', %s)
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
                        tempo_fine_asta = (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day'
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

    # In altri casi, restituisci None o la rappresentazione testuale
    return str(data_input)


