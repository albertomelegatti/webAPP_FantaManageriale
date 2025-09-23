import os
import psycopg2
import secrets
from flask import Flask, render_template, send_from_directory, request, session, flash, redirect, url_for
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Pagina principale
@app.route("/")
def home():
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

        conn = get_connection()
        cur = conn.cursor()

        if username == "admin":
            cur.execute("SELECT hash_password FROM admin WHERE username = %s", (username,))
            row = cur.fetchone()
            if row and check_password_hash(row[0], password):
                cur.close()
                conn.close()
                session['username'] = username  # Memorizza l'username nella sessione
                return render_template("admin.html")
            else:
                flash("Credenziali admin errate.", "danger")

        else:
            cur.execute("SELECT hash_password, nome FROM squadra WHERE username = %s", (username,))
            row = cur.fetchone()
            print(row)
            if row is not None:
                hash_password, nome_squadra = row
                if check_password_hash(hash_password, password):
                    session['username'] = username  # Memorizza l'username nella sessione
                    cur.close()
                    conn.close()
                    return render_template("squadraLogin.html", nome_squadra=nome_squadra)
                else:
                    flash("Password errata.", "danger")
            else:
                flash("Username non trovato.", "danger")

        cur.close()
        conn.close()
        return redirect(url_for('login'))

    return render_template("login.html", error=error)


# Rotta per area squadre
@app.route("/login-squadre")
def login_squadre():
    return render_template("squadre.html")


# Pagine squadre placeholder
@app.route("/squadre")
def squadre():
    conn = get_connection()
    cur = conn.cursor()

    # Prendi i dati dal database
    cur.execute("SELECT nome FROM squadra ORDER BY nome ASC;")
    squadre = [row[0] for row in cur.fetchall()]  # lista di nomi di squadre

    cur.close()
    conn.close()

    return render_template("squadre.html", squadre=squadre)


@app.route("/squadra/<nome_squadra>")
def dashboardSquadra(nome_squadra):
    conn = get_connection()
    cur = conn.cursor()

    # Prendi i giocatori della rosa direttamente
    #cur.execute("""
        #SELECT nome, ruolo, valore
        #FROM giocatori
        #WHERE squadra_nome = %s
        #ORDER BY ruolo ASC;
    #""", (nome_squadra,))
    #rosa = cur.fetchall()
    rosa = []

    cur.close()
    conn.close()

    return render_template("dashboardSquadra.html", nome_squadra=nome_squadra, rosa=rosa)



@app.route("/creditiStadi")
def creditiStadi():
    conn = get_connection()
    cur = conn.cursor()

    # Prendi i dati dal database
    cur.execute("SELECT nome, proprietario, livello, capacità FROM stadio ORDER BY nome ASC;")
    stadi_raw = cur.fetchall()  # lista di tuple

    stadi = []
    for s in stadi_raw:
        nome = s['nome']
        proprietario = s['proprietario']
        livello = s['livello']
        capacita = int(s['capacità'])
        
        if capacita < 30000:
            bonus = "+0"
        elif 30000 <= capacita < 60000:
            bonus = "+0,5"
        elif 60000 <= capacita < 90000:
            bonus = "+1"
        elif 90000 <= capacita < 150000:
            bonus = "+1,5"
        else:
            bonus = "+2"

        stadi.append({
            "nome": nome,
            "proprietario": proprietario,
            "livello": livello,
            "capacità": capacita,
            "bonus": bonus,
            "crediti_giornalieri": int(capacita / 10000)
        })

    #print(stadi)
    cur.close()
    conn.close()

    return render_template("creditiStadi.html", stadi=stadi)


@app.route("/listone")
def listone():
    return render_template("listone.html")

@app.route("/aste")
def aste():
    return render_template("aste.html")

@app.route("/scarica_regolamento")
def scarica_regolamento():
    return send_from_directory(directory='static', path='regolamento.pdf', as_attachment=True)


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

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT hash_password FROM squadra WHERE username = %s", (username,))
        row = cur.fetchone()

        if row is not None:
            print(row[0])
            if check_password_hash(row[0], old_password):
                new_hashed_password = generate_password_hash(new_password)
                cur.execute("UPDATE squadra SET hash_password = %s WHERE username = %s", (new_hashed_password, username))
                conn.commit()
                nome_squadra = cur.execute("SELECT nome FROM squadra WHERE username = %s", (username,))
                nome_squadra = cur.fetchone()[0]
                cur.close()
                conn.close()
                return render_template("squadraLogin.html", nome_squadra=nome_squadra, message="Password cambiata con successo.")

        cur.close()
        conn.close()
        flash("Errore nel cambio password.", "danger")
        return redirect(url_for('cambia_password'))

    return render_template("changePassword.html")


if __name__ == "__main__":
    # Specificare host per Render
    app.run(host="0.0.0.0", port=8080, debug=True)
