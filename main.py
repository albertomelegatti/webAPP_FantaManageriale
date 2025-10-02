import os
import psycopg2
import secrets
from flask import Flask, render_template, send_from_directory, request, session, flash, redirect, url_for, jsonify
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
#from chatbot import Chatbot

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)

app = Flask(__name__)
#chatbot = Chatbot()
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
            cur.execute('''SELECT hash_password 
                        FROM admin 
                        WHERE username = %s''', (username,))
            row = cur.fetchone()
            if row and check_password_hash(row[0], password):
                cur.close()
                conn.close()
                session['username'] = username  # Memorizza l'username nella sessione
                return redirect(url_for('admin'))
            else:
                flash("Credenziali admin errate.", "danger")

        else:
            cur.execute('''SELECT hash_password, nome 
                        FROM squadra 
                        WHERE username = %s''', (username,))
            row = cur.fetchone()
            print(row)
            if row is not None:
                hash_password, nome_squadra = row
                if check_password_hash(hash_password, password):
                    session['username'] = username  # Memorizza l'username nella sessione
                    cur.close()
                    conn.close()
                    return redirect(url_for('squadraLogin', nome_squadra=nome_squadra))
                else:
                    flash("Password errata.", "danger")
            else:
                flash("Username non trovato.", "danger")

        cur.close()
        conn.close()
        return redirect(url_for('login'))

    return render_template("login.html", error=error)


# Rotta per area admin
@app.route("/admin")
def admin():
    return render_template("admin.html")


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
    cur.execute('''SELECT nome 
                FROM squadra 
                WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
    squadre = [row[0] for row in cur.fetchall()]  # lista di nomi di squadre

    cur.close()
    conn.close()

    return render_template("squadre.html", squadre=squadre)


@app.route("/squadra/<nome_squadra>")
def dashboardSquadra(nome_squadra):
    conn = get_connection()
    cur = conn.cursor()

    stadio = []
    squadra = []

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
    username = squadra_raw[0]
    crediti = squadra_raw[1]

    # CONTEGGIO SLOT OCCUPATI
    cur.execute('''SELECT COUNT(id) AS slotOccupati 
                FROM giocatore 
                WHERE squadra_att = %s 
                    AND tipo_contratto IN ('Hold', 'Indeterminato');''', (nome_squadra,))
    slotOccupati = cur.fetchone()[0]
    
    # ROSA
    rosa = []
    cur.execute('''SELECT nome, tipo_contratto, ruolo, quot_att_mantra 
                FROM giocatore 
                WHERE squadra_att = %s 
                    AND tipo_contratto <> 'Primavera';''' , (nome_squadra,))
    rosa_raw = cur.fetchall()

    for g in rosa_raw:
        nome = g['nome']
        tipo_contratto = g['tipo_contratto']
        ruolo = g['ruolo']
        ruolo = ruolo.strip("{}")
        quot_att_mantra = g['quot_att_mantra']
        rosa.append({
            "nome": nome,
            "tipo_contratto": tipo_contratto,
            "ruolo": ruolo,
            "quot_att_mantra": quot_att_mantra
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
        tipo_contratto = g['tipo_contratto']
        ruolo = g['ruolo']
        ruolo = ruolo.strip("{}")
        quot_att_mantra = g['quot_att_mantra']
        primavera.append({
            "nome": nome,
            "ruolo": ruolo,
            "quot_att_mantra": quot_att_mantra
        })


    # CONTEGGIO PRESTITI IN
    cur.execute('''SELECT COUNT(id)
                FROM giocatore
                WHERE squadra_att = %s 
                    AND tipo_contratto = 'Fanta-Prestito';''', (nome_squadra,))
    prestiti_in_num = cur.fetchone()[0]

    # PRESTITI IN
    prestiti_in = []
    cur.execute('''SELECT nome, ruolo, quot_att_mantra, detentore_cartellino
                FROM giocatore 
                WHERE squadra_att = %s 
                    AND tipo_contratto = 'Fanta-Prestito';''', (nome_squadra,))
    prestiti_in_raw = cur.fetchall()

    for g in prestiti_in_raw:
        nome = g['nome']
        ruolo = g['ruolo']
        ruolo = ruolo.strip("{}")
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
    print(prestiti_out_raw)

    for g in prestiti_out_raw:
        nome = g['nome']
        ruolo = g['ruolo']
        ruolo = ruolo.strip("{}")
        quot_att_mantra = g['quot_att_mantra']
        squadra_att = g['squadra_att']
        prestiti_out.append({
            "nome": nome,
            "ruolo": ruolo,
            "quot_att_mantra": quot_att_mantra,
            "squadra_att": squadra_att
        })
    
    

    cur.close()
    conn.close()

    return render_template("dashboardSquadra.html", nome_squadra=nome_squadra, rosa=rosa, primavera=primavera,prestiti_in=prestiti_in, prestiti_in_num=prestiti_in_num, prestiti_out=prestiti_out, stadio=stadio, username=username, crediti=crediti, squadra=squadra, slotOccupati=slotOccupati)



@app.route("/creditiStadi")
def creditiStadi():
    conn = get_connection()
    cur = conn.cursor()

    # Prendo la quantità di crediti per ogni squadra
    cur.execute('''SELECT nome, crediti 
                FROM squadra 
                WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
    squadre_raw = cur.fetchall()  # lista di tuple
    squadre = []
    for c in squadre_raw:
        nome = c['nome']
        crediti = c['crediti']
        squadre.append({
            "nome": nome,
            "crediti": crediti
        })



    # Prendi i dati dal database
    cur.execute('''SELECT nome, proprietario, livello 
                FROM stadio ORDER BY nome ASC;''')
    stadi_raw = cur.fetchall()  # lista di tuple

    stadi = []
    for s in stadi_raw:
        nome = s['nome']
        proprietario = s['proprietario']
        livello = s['livello']
        
        if livello == 0:
            bonus = 0
        elif livello == 1:
            bonus = 4
        elif livello == 2:
            bonus = 8
        elif livello == 3:
            bonus = 14
        elif livello == 4:
            bonus = 18
        elif livello == 5:
            bonus = 25
        elif livello == 6:
            bonus = 30
        elif livello == 7:
            bonus = 39
        elif livello == 8:
            bonus = 44


        stadi.append({
            "proprietario": proprietario,
            "nome": nome,
            "livello": livello,
            "crediti_annuali": bonus
        })

    cur.close()
    conn.close()

    return render_template("creditiStadi.html", stadi=stadi, squadre=squadre)


@app.route("/listone")
def listone():
    # Collegamento al google sheet
    







    return render_template("listone.html")

@app.route("/squadraLogin/<nome_squadra>")
def squadraLogin(nome_squadra):
    return render_template("squadraLogin.html", nome_squadra=nome_squadra)

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

        conn = get_connection()
        cur = conn.cursor()

        cur.execute('''SELECT hash_password 
                    FROM squadra 
                    WHERE username = %s''', (username,))
        row = cur.fetchone()

        if row is not None:
            print(row[0])
            if check_password_hash(row[0], old_password):
                new_hashed_password = generate_password_hash(new_password)
                cur.execute('''UPDATE squadra 
                            SET hash_password = %s 
                            WHERE username = %s''', (new_hashed_password, username))
                conn.commit()
                nome_squadra = cur.execute('''SELECT nome 
                                           FROM squadra 
                                           WHERE username = %s''', (username,))
                nome_squadra = cur.fetchone()[0]
                cur.close()
                conn.close()
                return redirect(url_for('squadraLogin', nome_squadra=nome_squadra))

        cur.close()
        conn.close()
        flash("Errore nel cambio password.", "danger")
        return redirect(url_for('cambia_password'))

    return render_template("changePassword.html")

@app.route("/chat")
def chat_page():
    return render_template("chat.html")  # Pagina HTML con la chat

@app.route("/ask", methods=["POST"])
def ask():
    print("SDROGO")
    user_question = request.json.get("question")  # <-- così leggi il JSON
    print("Domanda:", user_question)  # Stampa a terminale
    answer = chatbot.get_answer(user_question)
    print("Risposta:", answer)       # Stampa a terminale
    return jsonify({"answer": answer})




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
