import secrets
import psycopg2
import time
from flask import Flask, render_template, send_from_directory, request, session, flash, redirect, url_for, jsonify, current_app
from flask_session import Session
from psycopg2 import extensions
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from admin import admin_bp
from user import user_bp, format_partecipanti, formatta_data
from user_aste import aste_bp
from user_mercato import mercato_bp
from user_prestiti import prestiti_bp
from user_rosa import rosa_bp
from automatic_routes import automatic_routes_bp
from db import get_connection, release_connection, init_pool
from telegram_utils import get_all_telegram_ids
from datetime import datetime
from chatbot import get_answer
from queries import get_slot_occupati


app = Flask(__name__)

init_pool()

app.secret_key = secrets.token_hex(16)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 7
app.config['SQUADRE_TELEGRAM_IDS'] = get_all_telegram_ids() # Per accedere: current_app.config.get('SQUADRE_TELEGRAM_IDS', {})

Session(app)

app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)
app.register_blueprint(aste_bp)
app.register_blueprint(mercato_bp)
app.register_blueprint(prestiti_bp)
app.register_blueprint(rosa_bp)
app.register_blueprint(automatic_routes_bp)




# Pagina principale
@app.route("/")
def home():
    return render_template("index.html")


# Rotta per login admin
@app.route("/login", methods=["GET", "POST"])
def login():

    # Se l'utente è già loggato, viene mandato alla schermata giusta
    if session.get("logged_in"):
        if session.get("is_admin"):
            return redirect(url_for('admin.admin_home'))
        elif session.get("nome_squadra"):
            return redirect(url_for('user.squadraLogin', nome_squadra=session["nome_squadra"]))
        return redirect(url_for('home'))
    
    error = None


    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("❌ Compila tutti i campi.", "danger")
            return redirect(url_for('login'))

        conn = None
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
                        session.permanent = True
                        return redirect(url_for('user.squadraLogin', nome_squadra=nome_squadra))
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
                    SELECT nome 
                    FROM squadra 
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre = [row["nome"] for row in cur.fetchall()]

        return render_template("squadre.html", squadre=squadre)

    except Exception as e:
        print("Errore squadre:", e)
        flash("❌ Errore nel recupero squadre.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)


@app.route("/squadra/<nome_squadra>")
def dashboardSquadra(nome_squadra):

    conn = None
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

        # CONTEGGIO SLOT OCCUPATI
        slot_occupati = get_slot_occupati(conn, nome_squadra)

        # ROSA
        rosa = []
        cur.execute('''
                    SELECT nome, tipo_contratto, ruolo, quot_att_mantra, costo 
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
                "costo": g['costo']
            })

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

        # CONTEGGIO PRESTITI IN
        cur.execute('''
                    SELECT COUNT(id) AS prestiti_in_num
                    FROM giocatore
                    WHERE squadra_att = %s 
                        AND tipo_contratto = 'Fanta-Prestito';
        ''', (nome_squadra,))
        prestiti_in_num = cur.fetchone()["prestiti_in_num"]

        # PRESTITI IN
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

        # PRESTITI OUT
        prestiti_out = []
        cur.execute('''
                    SELECT nome, ruolo, quot_att_mantra, squadra_att
                    FROM giocatore 
                    WHERE detentore_cartellino = %s 
                        AND tipo_contratto = 'Fanta-Prestito';
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

        return render_template(
            "dashboardSquadra.html",
            nome_squadra=nome_squadra,
            rosa=rosa,
            primavera=primavera,
            prestiti_in=prestiti_in,
            prestiti_in_num=prestiti_in_num,
            prestiti_out=prestiti_out,
            stadio=stadio,
            username=username,
            crediti=crediti,
            squadra=[],
            slot_occupati=slot_occupati
        )

    except Exception as e:
        print("Errore dashboardSquadra:", e)
        flash("❌ Errore nel caricamento della squadra.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)


@app.route("/creditiStadi")
def creditiStadiSlot():

    conn = None
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
                    FROM stadio ORDER BY nome ASC;''')
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

        # CONTEGGIO SLOT OCCUPATI
        cur.execute('''
                    SELECT squadra_att, COUNT(id) AS slot_occupati
                    FROM giocatore
                    WHERE tipo_contratto IN ('Hold', 'Indeterminato')
                    GROUP BY squadra_att;''')
        slot_raw = cur.fetchall()
        slot = []
        for s in slot_raw:
            slot.append({
                "squadra_att": s["squadra_att"],
                "slot_occupati": s["slot_occupati"]
            })


        return render_template("creditiStadiSlot.html", stadi=stadi, squadre=squadre, slot=slot)

    except Exception as e:
        print("Errore creditiStadi:", e)
        flash("❌ Errore nel caricamento dati stadi.", "danger")
        return redirect(url_for('home'))

    finally:
        release_connection(conn, cur)


@app.route("/listone")
def listone():
    link_fantacalcio_it = "https://www.fantacalcio.it/quotazioni-fantacalcio"
    return redirect(link_fantacalcio_it)


@app.route("/aste")
def aste():

    conn = None
    aste = []
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory = RealDictCursor)
    
        cur.execute('''
                    WITH giocatori_svincolati AS (
                        SELECT id, nome
                        FROM giocatore
                        WHERE tipo_contratto = 'Svincolato')
                    
                    SELECT g.nome, a.squadra_vincente, a.ultima_offerta, a.tempo_fine_asta, a.tempo_fine_mostra_interesse, a.stato, a.partecipanti
                    FROM asta a
                    JOIN giocatori_svincolati g ON a.giocatore = g.id;''')
        aste_raw = cur.fetchall()

        for a in aste_raw:

            data_scadenza = formatta_data(a["tempo_fine_asta"])
            tempo_fine_mostra_interesse = formatta_data(a["tempo_fine_mostra_interesse"])

            partecipanti = format_partecipanti(a["partecipanti"])

            aste.append({
                "giocatore": a["nome"],
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


                return redirect(url_for('user.squadraLogin', nome_squadra=nome_squadra))

            flash("❌ Errore nel cambio password.", "danger")

        except Exception as e:
            print("Errore cambio password:", e)
            flash("❌ Errore durante l'aggiornamento della password.", "danger")

        finally:
            release_connection(conn, cur)

        return redirect(url_for('cambia_password'))

    return render_template("changePassword.html")


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

