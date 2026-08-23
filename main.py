import psycopg2
import telegram_utils
import os
import time
from dotenv import load_dotenv
from flask import Flask, render_template, send_from_directory, request, session, flash, redirect, url_for, jsonify
from flask_compress import Compress
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from admin import admin_bp
from user import user_bp, format_partecipanti, formatta_data
from user_aste import aste_bp
from user_mercato import mercato_bp
from user_prestiti import prestiti_bp
from user_rosa import rosa_bp
from webhook import webhook_bp
from vetrina import vetrina_bp
from db import get_connection, release_connection, init_pool
from telegram_utils import get_all_telegram_ids
from queries import get_slot_giocatori, get_slot_aste, ruolo_sort_key, ruolo_base_sort_key
from chatbot import get_answer

app = Flask(__name__)

load_dotenv()
init_pool()

app.secret_key = os.getenv("SECRET_KEY", "chiave_segreta_default_per_sviluppo")

app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 30  # 30 giorni invece di 365
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Cache lato browser per gli asset statici (CSS/JS/immagini) e compressione gzip/br delle risposte
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 1  # 1 giorno di cache su immagini statiche
Compress(app)


_asset_v_cache = {}
_ASSET_V_TTL = 5  # secondi: evita uno stat() del file a ogni singola riga/richiesta

def asset_v(rel_path):
    """Timestamp di modifica di un file statico, da usare come ?v= per invalidare la cache del browser quando il file cambia.

    Il risultato viene tenuto in cache per qualche secondo: senza, una pagina con
    molte righe (es. la Rosa con 25-30 giocatori) farebbe uno stat() del
    filesystem per ogni riga a ogni caricamento.
    """
    now = time.monotonic()
    cached = _asset_v_cache.get(rel_path)
    if cached and now - cached[1] < _ASSET_V_TTL:
        return cached[0]

    try:
        value = int(os.path.getmtime(os.path.join(app.static_folder, rel_path)))
    except OSError:
        value = 0

    _asset_v_cache[rel_path] = (value, now)
    return value


app.jinja_env.globals['asset_v'] = asset_v

# Inizializza il dizionario telegram al lancio dell'app
app.config['SQUADRE_TELEGRAM_IDS'] = get_all_telegram_ids()

app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(aste_bp)
app.register_blueprint(mercato_bp)
app.register_blueprint(prestiti_bp)
app.register_blueprint(rosa_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(vetrina_bp)


@app.errorhandler(500)
def handle_500(error):
    """Handler specifico per errori 500"""
    return redirect(url_for('home')), 500


# Pagina principale
@app.route("/")
def home():
    return render_template("index.html")


# Health check endpoint per Render
@app.route("/health")
def health_check():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        release_connection(conn, cur)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Health check failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Rotta per login admin
@app.route("/login", methods=["GET", "POST"])
def login():

    # Se l'utente è già loggato, viene mandato alla schermata giusta
    if session.get("logged_in"):
        if session.get("is_admin"):
            return redirect(url_for('admin.admin_home'))
        elif session.get("nome_squadra"):
            return redirect(url_for('user.squadra_login', nome_squadra=session["nome_squadra"]))
        return redirect(url_for('home'))
    
    error = None


    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("❌ Compila tutti i campi.", "danger")
            return redirect(url_for('login'))

        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Login admin
            if username == "admin":
                cur.execute('''
                            SELECT hash_password 
                            FROM admin 
                            WHERE username = %s;
                ''', (username,))
                row = cur.fetchone()

                if row and check_password_hash(row["hash_password"], password):
                    session.clear()
                    session["logged_in"] = True
                    session["is_admin"] = True
                    session["username"] = username
                    session.permanent = True
                    return redirect(url_for('admin.admin_home'))
                
                else:
                    flash("❌ Credenziali admin errate.", "danger")

            # Login squadra
            else:
                cur.execute('''
                            SELECT hash_password, nome 
                            FROM squadra 
                            WHERE username = %s;
                ''', (username,))
                row = cur.fetchone()

                if row is not None:
                    hash_password = row["hash_password"]
                    nome_squadra = row["nome"]
                    if check_password_hash(hash_password, password):
                        session.clear()
                        session["logged_in"] = True
                        session["nome_squadra"] = row["nome"]
                        session["is_admin"] = False
                        session["username"] = username
                        session.permanent = True
                        return redirect(url_for('user.squadra_login', nome_squadra=nome_squadra))
                    else:
                        flash("❌ Password errata.", "danger")
                else:
                    flash("❌ Username non trovato.", "danger")

        except Exception as e:
            print("Errore login:", e)
            flash("❌ Errore di connessione al database.", "danger")

        finally:
            release_connection(conn, cur)

        return redirect(url_for('login'))

    return render_template("login.html", error=error)



@app.route("/logout")
def logout():
    session.clear()
    flash("✅ Hai effettuato il logout.", "success")
    return redirect(url_for("login"))


# Schermata squadre con bottoni
@app.route("/squadre")
def squadre():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT nome, username
                    FROM squadra
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre = [{"nome": row["nome"], "username": row["username"]} for row in cur.fetchall()]

        return render_template("squadre.html", squadre=squadre)

    except Exception as e:
        print("Errore squadre:", e)
        flash("❌ Errore nel recupero squadre.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)


@app.route("/squadra/<nome_squadra>")
def dashboard_squadra(nome_squadra):

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # STADIO
        cur.execute('''
                    SELECT nome, proprietario, livello 
                    FROM stadio 
                    WHERE proprietario = %s;
        ''', (nome_squadra,))
        stadio = cur.fetchone()

        # CREDITI
        cur.execute('''
                    SELECT username, crediti 
                    FROM squadra 
                    WHERE nome = %s;
        ''', (nome_squadra,))
        squadra_raw = cur.fetchone()
        username = squadra_raw["username"]
        crediti = squadra_raw["crediti"]

        # CONTEGGIO SLOT GIOCATORI E ASTE (slot_occupati = somma dei due, evita di ricalcolare slot_giocatori due volte)
        slot_giocatori = get_slot_giocatori(conn, nome_squadra)
        slot_aste = get_slot_aste(conn, nome_squadra)
        slot_occupati = slot_giocatori + slot_aste

        # ROSA
        rosa = []
        cur.execute('''
                    SELECT nome, tipo_contratto, ruolo, quot_att_mantra, costo, club
                    FROM giocatore
                    WHERE squadra_att = %s
                        AND tipo_contratto <> 'Primavera';
        ''' , (nome_squadra,))
        rosa_raw = cur.fetchall()

        for g in rosa_raw:
            ruolo = g['ruolo'].strip("{}")
            rosa.append({
                "nome": g['nome'],
                "tipo_contratto": g['tipo_contratto'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra'],
                "costo": g['costo'],
                "club": g['club']
            })

        rosa.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        # PRIMAVERA
        primavera = []
        cur.execute('''
                    SELECT nome, tipo_contratto, ruolo, quot_att_mantra 
                    FROM giocatore 
                    WHERE squadra_att = %s 
                        AND tipo_contratto = 'Primavera';
        ''' , (nome_squadra,))
        primavera_raw = cur.fetchall()

        for g in primavera_raw:
            ruolo = g['ruolo'].strip("{}")
            primavera.append({
                "nome": g['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra']
            })

        primavera.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        # PRESTITI IN (prestiti_in_num ricavato da len(), evita una COUNT separata con la stessa WHERE)
        prestiti_in = []
        cur.execute('''
                    SELECT nome, ruolo, quot_att_mantra, detentore_cartellino
                    FROM giocatore
                    WHERE squadra_att = %s
                        AND tipo_contratto = 'Fanta-Prestito';
        ''', (nome_squadra,))
        prestiti_in_raw = cur.fetchall()

        for g in prestiti_in_raw:
            ruolo = g['ruolo'].strip("{}")
            prestiti_in.append({
                "nome": g['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra'],
                "detentore_cartellino": g["detentore_cartellino"]
            })

        prestiti_in.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        prestiti_in_num = len(prestiti_in)

        # DRAFT - pick detenute dalla squadra
        draft_pick = []
        cur.execute('''
                    SELECT d.detentore_originale, d.anno, d.numero, g.nome AS giocatore_scelto
                    FROM draft d
                    LEFT JOIN giocatore g
                        ON d.id_giocatore_scelto = g.id
                    WHERE d.detentore_att = %s
                    ORDER BY d.anno, d.numero;
        ''', (nome_squadra,))
        draft_pick_raw = cur.fetchall()

        for p in draft_pick_raw:
            anno = p['anno'].year if hasattr(p['anno'], 'year') else p['anno']
            draft_pick.append({
                "detentore_originale": p["detentore_originale"],
                "anno": anno,
                "numero": p["numero"],
                "giocatore_scelto": p["giocatore_scelto"] or "—"
            })

        # PRESTITI OUT
        prestiti_out = []
        cur.execute('''
                    SELECT nome, ruolo, quot_att_mantra, squadra_att
                    FROM giocatore 
                    WHERE detentore_cartellino = %s 
                        AND tipo_contratto in ('Fanta-Prestito', 'Prestito Reale');
        ''', (nome_squadra,))
        prestiti_out_raw = cur.fetchall()

        for g in prestiti_out_raw:
            ruolo = g['ruolo'].strip("{}")
            prestiti_out.append({
                "nome": g['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra'],
                "squadra_att": g['squadra_att']
            })

        prestiti_out.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        # MOVIMENTI DI MERCATO
        mercato = []
        cur.execute('''
                SELECT data, evento, stagione
                FROM movimenti_squadra
                WHERE evento ILIKE %s and evento not ilike '%%🏷️ ASTA%%'
                ORDER BY data DESC;
        ''', (f'%{nome_squadra}%',))
        mercato_raw = cur.fetchall()

        for m in mercato_raw:
            mercato.append({
                "data": m['data'],
                "evento": m['evento'],
                "stagione": m['stagione']
            })

        return render_template(
            "dashboard_squadra.html",
            nome_squadra=nome_squadra,
            rosa=rosa,
            primavera=primavera,
            prestiti_in=prestiti_in,
            prestiti_in_num=prestiti_in_num,
            draft_pick=draft_pick,
            prestiti_out=prestiti_out,
            stadio=stadio,
            username=username,
            crediti=crediti,
            squadra=[],
            slot_occupati=slot_occupati,
            slot_giocatori=slot_giocatori,
            mercato=mercato
        )

    except Exception as e:
        print("Errore dashboard Squadra:", e)
        flash("❌ Errore nel caricamento della squadra.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)




# Visualizza tutti gli eventi di mercato con filtri per stagione ed evento
@app.route("/movimenti_mercato")
def movimenti_mercato():

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupera tutti gli eventi di mercato
        cur.execute('''
                    SELECT data, evento, stagione
                    FROM movimenti_squadra
                    WHERE evento NOT ILIKE '%%🏷️ ASTA%%'
                    ORDER BY data DESC;
        ''')
        mercato_raw = cur.fetchall()

        mercato = []
        for m in mercato_raw:
            mercato.append({
                "data": m['data'],
                "evento": m['evento'],
                "stagione": m['stagione']
            })

        # Recupera tutte le squadre (eccetto Svincolato)
        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome <> 'Svincolato'
                    ORDER BY nome ASC;
        ''')
        squadre_raw = cur.fetchall()
        squadre = [row['nome'] for row in squadre_raw]

        return render_template(
            "movimenti_mercato.html",
            mercato=mercato,
            squadre=squadre
        )

    except Exception as e:
        print("Errore movimenti_mercato:", e)
        flash("❌ Errore nel recupero dei movimenti di mercato.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)
        


@app.route("/crediti_stadi_slot")
def crediti_stadi_slot():

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # CREDITI
        cur.execute('''
                    SELECT nome, crediti
                    FROM squadra
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre_raw = cur.fetchall()
        squadre = [{"nome": c['nome'], "crediti": c['crediti']} for c in squadre_raw]

        # STADIO
        cur.execute('''
                    SELECT nome, proprietario, livello
                    FROM stadio ORDER BY proprietario ASC;''')
        stadi_raw = cur.fetchall()
        stadi = []
        for s in stadi_raw:
            livello = s['livello']
            bonus = [0,4,8,14,18,25,30,39,44][livello] if livello <= 8 else 0
            stadi.append({
                "proprietario": s['proprietario'],
                "nome": s['nome'],
                "livello": livello,
                "crediti_annuali": bonus
            })

        # CONTEGGIO SLOT OCCUPATI E IN PRESTITO
        cur.execute('''
                    SELECT squadra_att, COUNT(id) AS slot_occupati
                    FROM giocatore
                    WHERE tipo_contratto IN ('Hold', 'Indeterminato')
                    GROUP BY squadra_att;''')
        slot_raw = cur.fetchall()

        cur.execute('''
                    SELECT squadra_att, COUNT(id) AS slot_in_prestito
                    FROM giocatore
                    WHERE tipo_contratto = 'Fanta-Prestito'
                    GROUP BY squadra_att;''')
        slot_prestito_raw = cur.fetchall()
        slot_prestito_dict = {s["squadra_att"]: s["slot_in_prestito"] for s in slot_prestito_raw}

        slot = []
        for s in slot_raw:
            slot.append({
                "squadra_att": s["squadra_att"],
                "slot_occupati": s["slot_occupati"],
                "slot_in_prestito": slot_prestito_dict.get(s["squadra_att"], 0)
            })


        return render_template("crediti_stadi_slot.html", stadi=stadi, squadre=squadre, slot=slot)

    except Exception as e:
        print("Errore crediti stadi e slot:", e)
        flash("❌ Errore nel caricamento dati stadi.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)


@app.route("/listone")
def listone():
    conn = None
    cur = None
    giocatori = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT g.nome, g.ruolo, g.club, g.squadra_att, g.tipo_contratto, g.quot_att_mantra, s.username AS squadra_username
            FROM giocatore g
            LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
            WHERE g.priorita = 1
            ORDER BY g.quot_att_mantra DESC;
        """)
        giocatori = [
            {
                "nome": g["nome"],
                "ruolo": (g["ruolo"] or "").strip("{}"),
                "club": g["club"],
                "squadra_att": g["squadra_att"],
                "squadra_username": g["squadra_username"],
                "tipo_contratto": g["tipo_contratto"],
                "quotazione": g["quot_att_mantra"],
            }
            for g in cur.fetchall()
        ]

    except Exception as e:
        print("Errore caricamento listone:", e)
        flash("❌ Errore durante il caricamento del listone.", "danger")

    finally:
        release_connection(conn, cur)

    ruoli_base = set()
    for g in giocatori:
        for token in g["ruolo"].split(","):
            token = token.strip()
            if token:
                ruoli_base.add(token)
    ruoli_disponibili = sorted(ruoli_base, key=ruolo_base_sort_key)

    club_disponibili = sorted({g["club"] for g in giocatori if g["club"]})
    squadre_disponibili = sorted({g["squadra_att"] for g in giocatori if g["squadra_att"]})
    contratti_disponibili = sorted({g["tipo_contratto"] for g in giocatori if g["tipo_contratto"]})

    return render_template("listone.html",
                            giocatori=giocatori,
                            ruoli_disponibili=ruoli_disponibili,
                            club_disponibili=club_disponibili,
                            squadre_disponibili=squadre_disponibili,
                            contratti_disponibili=contratti_disponibili)


@app.route("/aste")
def aste():

    conn = None
    cur = None
    aste = []
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory = RealDictCursor)
    
        cur.execute('''
                    SELECT g.nome, g.ruolo, g.club, a.squadra_vincente, a.ultima_offerta, a.tempo_fine_asta, a.tempo_fine_mostra_interesse, a.stato, a.partecipanti
                    FROM asta a
                    JOIN giocatore g ON a.giocatore = g.id
                    ORDER BY a.tempo_fine_asta DESC;''')
        aste_raw = cur.fetchall()

        for a in aste_raw:

            data_scadenza = formatta_data(a["tempo_fine_asta"])
            tempo_fine_mostra_interesse = formatta_data(a["tempo_fine_mostra_interesse"])

            partecipanti = format_partecipanti(a["partecipanti"])

            aste.append({
                "giocatore": a["nome"],
                "ruolo": a["ruolo"].strip("{}"),
                "club": a["club"],
                "squadra_vincente": a["squadra_vincente"],
                "ultima_offerta": a["ultima_offerta"],
                "tempo_fine_mostra_interesse": tempo_fine_mostra_interesse,
                "data_scadenza": data_scadenza,
                "stato": a["stato"],
                "partecipanti": partecipanti
            })
    
    
    except Exception as e:
        print("Errore lista aste generale:", e)
        flash("❌ Errore nella creazione lista aste.", "danger")
        return redirect(url_for('home'))
    
    finally:
        release_connection(conn, cur)

    return render_template("aste.html", aste=aste)




@app.route("/scarica_regolamento")
def vedi_regolamento():
    return send_from_directory('static', 'regolamento.pdf', mimetype='application/pdf', as_attachment=False)


@app.route('/cambia_password', methods=['GET', 'POST'])
def cambia_password():

    if request.method == 'POST':
        username = session.get('username')
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash("❌ Le password non corrispondono.", "danger")
            return redirect(url_for('cambia_password'))

        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute('''
                        SELECT hash_password 
                        FROM squadra 
                        WHERE username = %s;
            ''', (username,))
            row = cur.fetchone()

            if row and check_password_hash(row["hash_password"], old_password):
                new_hashed_password = generate_password_hash(new_password)

                cur.execute('''
                            UPDATE squadra 
                            SET hash_password = %s 
                            WHERE username = %s;
                ''', (new_hashed_password, username))
                conn.commit()

                cur.execute('''
                            SELECT nome 
                            FROM squadra 
                            WHERE username = %s;
                ''', (username,))
                nome_squadra = cur.fetchone()["nome"]


                return redirect(url_for('user.squadra_login', nome_squadra=nome_squadra))

            flash("❌ Errore nel cambio password.", "danger")

        except Exception as e:
            print("Errore cambio password:", e)
            flash("❌ Errore durante l'aggiornamento della password.", "danger")

        finally:
            release_connection(conn, cur)

        return redirect(url_for('cambia_password'))

    return render_template("change_password.html")


@app.route("/keepalive", methods=["GET", "POST"])
def keepalive():
        telegram_utils.send_message(903944311)
        return render_template("index.html")




chat_history = []

@app.route("/chat", methods=["GET", "POST"])
def chat_page():
    global chat_history

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        user_msg = data.get("question", "").strip()

        if not user_msg:
            return jsonify({"answer": "⚠️ Inserisci una domanda valida."})

        bot_msg = get_answer(user_msg)

        chat_history.append((user_msg, bot_msg))
        chat_history = chat_history[-2:]

        return jsonify({"answer": bot_msg})

    return render_template("chat.html")



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
