import secrets
from flask import Flask, render_template, send_from_directory, request, session, flash, redirect, url_for, jsonify
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from admin import admin_bp
from user import user_bp
from db import get_connection, release_connection, init_pool, keep_awake
import time
# from chatbot import Chatbot

app = Flask(__name__)

# chatbot = Chatbot()
app.secret_key = secrets.token_hex(16)


app.register_blueprint(admin_bp)
app.register_blueprint(user_bp)

time.sleep(8)
init_pool()


# Pagina principale
@app.route("/")
def home():
    #keep_awake()
    return render_template("index.html")



# Rotta per login admin
@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("Compila tutti i campi.", "danger")
            return redirect(url_for('login'))

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            if username == "admin":
                cur.execute('''SELECT hash_password 
                            FROM admin 
                            WHERE username = %s''', (username,))
                row = cur.fetchone()
                if row and check_password_hash(row["hash_password"], password):

                    session['username'] = username
                    return redirect(url_for('admin.home_admin'))
                else:
                    flash("Credenziali admin errate.", "danger")

            else:
                cur.execute('''SELECT hash_password, nome 
                            FROM squadra 
                            WHERE username = %s''', (username,))
                row = cur.fetchone()

                if row is not None:
                    hash_password = row["hash_password"]
                    nome_squadra = row["nome"]
                    if check_password_hash(hash_password, password):
                        session['username'] = username
                        session["nome_squadra"] = nome_squadra
                        return redirect(url_for('user.squadraLogin', nome_squadra=nome_squadra))
                    else:
                        flash("Password errata.", "danger")
                else:
                    flash("Username non trovato.", "danger")

            cur.close()

        except Exception as e:
            print("Errore login:", e)
            flash("Errore di connessione al database.", "danger")

        finally:
            if conn:
                release_connection(conn)

        return redirect(url_for('login'))

    return render_template("login.html", error=error)


# Schermata squadre con bottoni
@app.route("/squadre")
def squadre():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''SELECT nome 
                    FROM squadra 
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre = [row["nome"] for row in cur.fetchall()]

        return render_template("squadre.html", squadre=squadre)

    except Exception as e:
        print("Errore squadre:", e)
        flash("Errore nel recupero squadre.", "danger")
        return redirect(url_for('home'))

    finally:
        if conn:
            release_connection(conn)


@app.route("/squadra/<nome_squadra>")
def dashboardSquadra(nome_squadra):
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # STADIO
        cur.execute('''SELECT nome, proprietario, livello 
                    FROM stadio 
                    WHERE proprietario = %s;''', (nome_squadra,))
        stadio = cur.fetchone()

        # CREDITI
        cur.execute('''SELECT username, crediti 
                    FROM squadra 
                    WHERE nome = %s;''', (nome_squadra,))
        squadra_raw = cur.fetchone()
        username = squadra_raw["username"]
        crediti = squadra_raw["crediti"]

        # CONTEGGIO SLOT OCCUPATI
        cur.execute('''SELECT COUNT(id) AS slot_occupati 
                    FROM giocatore 
                    WHERE squadra_att = %s 
                        AND tipo_contratto IN ('Hold', 'Indeterminato');''', (nome_squadra,))
        slotOccupati = cur.fetchone()["slot_occupati"]

        # ROSA
        rosa = []
        cur.execute('''SELECT nome, tipo_contratto, ruolo, quot_att_mantra, costo 
                    FROM giocatore 
                    WHERE squadra_att = %s 
                        AND tipo_contratto <> 'Primavera';''' , (nome_squadra,))
        rosa_raw = cur.fetchall()

        for g in rosa_raw:
            nome = g['nome']
            tipo_contratto = g['tipo_contratto']
            ruolo = g['ruolo'].strip("{}")
            quot_att_mantra = g['quot_att_mantra']
            costo = g['costo']
            rosa.append({
                "nome": nome,
                "tipo_contratto": tipo_contratto,
                "ruolo": ruolo,
                "quot_att_mantra": quot_att_mantra,
                "costo": costo
            })

        # PRIMAVERA
        primavera = []
        cur.execute('''SELECT nome, tipo_contratto, ruolo, quot_att_mantra 
                    FROM giocatore 
                    WHERE squadra_att = %s 
                        AND tipo_contratto = 'Primavera';''' , (nome_squadra,))
        primavera_raw = cur.fetchall()

        for g in primavera_raw:
            nome = g['nome']
            ruolo = g['ruolo'].strip("{}")
            quot_att_mantra = g['quot_att_mantra']
            primavera.append({
                "nome": nome,
                "ruolo": ruolo,
                "quot_att_mantra": quot_att_mantra
            })

        # CONTEGGIO PRESTITI IN
        cur.execute('''SELECT COUNT(id) AS prestiti_in_num
                    FROM giocatore
                    WHERE squadra_att = %s 
                        AND tipo_contratto = 'Fanta-Prestito';''', (nome_squadra,))
        prestiti_in_num = cur.fetchone()["prestiti_in_num"]

        # PRESTITI IN
        prestiti_in = []
        cur.execute('''SELECT nome, ruolo, quot_att_mantra, detentore_cartellino
                    FROM giocatore 
                    WHERE squadra_att = %s 
                        AND tipo_contratto = 'Fanta-Prestito';''', (nome_squadra,))
        prestiti_in_raw = cur.fetchall()

        for g in prestiti_in_raw:
            nome = g['nome']
            ruolo = g['ruolo'].strip("{}")
            quot_att_mantra = g['quot_att_mantra']
            detentore_cartellino = g["detentore_cartellino"]
            prestiti_in.append({
                "nome": nome,
                "ruolo": ruolo,
                "quot_att_mantra": quot_att_mantra,
                "detentore_cartellino": detentore_cartellino
            })

        # PRESTITI OUT
        prestiti_out = []
        cur.execute('''SELECT nome, ruolo, quot_att_mantra, squadra_att
                    FROM giocatore 
                    WHERE detentore_cartellino = %s 
                        AND tipo_contratto = 'Fanta-Prestito';''', (nome_squadra,))
        prestiti_out_raw = cur.fetchall()

        for g in prestiti_out_raw:
            nome = g['nome']
            ruolo = g['ruolo'].strip("{}")
            quot_att_mantra = g['quot_att_mantra']
            squadra_att = g['squadra_att']
            prestiti_out.append({
                "nome": nome,
                "ruolo": ruolo,
                "quot_att_mantra": quot_att_mantra,
                "squadra_att": squadra_att
            })

        cur.close()
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
            slotOccupati=slotOccupati
        )

    except Exception as e:
        print("Errore dashboardSquadra:", e)
        flash("Errore nel caricamento della squadra.", "danger")
        return redirect(url_for('home'))

    finally:
        if conn:
            release_connection(conn)


@app.route("/creditiStadi")
def creditiStadi():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''SELECT nome, crediti 
                    FROM squadra 
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre_raw = cur.fetchall()
        squadre = [{"nome": c['nome'], "crediti": c['crediti']} for c in squadre_raw]

        cur.execute('''SELECT nome, proprietario, livello 
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

        cur.close()
        return render_template("creditiStadi.html", stadi=stadi, squadre=squadre)

    except Exception as e:
        print("Errore creditiStadi:", e)
        flash("Errore nel caricamento dati stadi.", "danger")
        return redirect(url_for('home'))

    finally:
        if conn:
            release_connection(conn)


@app.route("/listone")
def listone():
    link_fantacalcio_it = "https://www.fantacalcio.it/quotazioni-fantacalcio"
    return redirect(link_fantacalcio_it)


@app.route("/aste")
def aste():
    return render_template("aste.html")


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
            flash("Le password non corrispondono.", "danger")
            return redirect(url_for('cambia_password'))

        conn = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute('''SELECT hash_password 
                        FROM squadra 
                        WHERE username = %s''', (username,))
            row = cur.fetchone()

            if row and check_password_hash(row["hash_password"], old_password):
                new_hashed_password = generate_password_hash(new_password)
                cur.execute('''UPDATE squadra 
                            SET hash_password = %s 
                            WHERE username = %s''', (new_hashed_password, username))
                conn.commit()

                cur.execute('''SELECT nome FROM squadra WHERE username = %s''', (username,))
                nome_squadra = cur.fetchone()["nome"]


                return redirect(url_for('user.squadraLogin', nome_squadra=nome_squadra))

            flash("Errore nel cambio password.", "danger")

        except Exception as e:
            print("Errore cambio password:", e)
            flash("Errore durante l'aggiornamento della password.", "danger")

        finally:
            if conn:
                release_connection(conn)

        return redirect(url_for('cambia_password'))

    return render_template("changePassword.html")


@app.route("/chat")
def chat_page():
    return render_template("chat.html")


@app.route("/ask", methods=["POST"])
def ask():
    print("SDROGO")
    user_question = request.json.get("question")
    print("Domanda:", user_question)
    answer = chatbot.get_answer(user_question)
    print("Risposta:", answer)
    return jsonify({"answer": answer})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)

