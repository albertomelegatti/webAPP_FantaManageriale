import os
import psycopg2
from flask import Flask, render_template, send_from_directory, request
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
print(f"Connessione al DB con {DATABASE_URL}")

#print(f"Connessione al DB con utente {USER} su host {HOST}:{PORT}, db {DBNAME}")

def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)

app = Flask(__name__)

# Credenziali admin
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

# Pagina principale
@app.route("/")
def home():
    return render_template("index.html")

# Rotta per login admin
@app.route("/login-admin", methods=["GET", "POST"])
def login_admin():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            return "<h2>Login riuscito! Benvenuto Admin 👋</h2>"
        else:
            return "<h2>Credenziali non valide. Riprova.</h2><a href='/login-admin'>Riprova</a>"
    
    # Se GET → mostra il form di login
    return render_template("adminLogin.html")

# Rotta per area squadre
@app.route("/login-squadre")
def login_squadre():
    return render_template("squadre.html")





# Pagine squadre placeholder
@app.route("/rose")
def rose():
    conn = get_connection()
    cur = conn.cursor()

    # Prendi i dati dal database
    cur.execute("SELECT nome FROM squadra ORDER BY nome ASC;")
    squadre = [row[0] for row in cur.fetchall()]  # lista di nomi di squadre

    cur.close()
    conn.close()


    return render_template("rose.html", squadre=squadre)





@app.route("/squadra/<nome_squadra>")
def mostra_rosa(nome_squadra):
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

    return render_template("rosa.html", nome_squadra=nome_squadra, rosa=rosa)



@app.route("/stadi")
def stadi():
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

    return render_template("stadi.html", stadi=stadi)





@app.route("/prestiti")
def prestiti():
    return "<h2>Sezione Prestiti (in costruzione)</h2>"

# Scarica regolamento
@app.route("/scarica-regolamento")
def scarica_regolamento():
    directory = os.path.join(app.root_path, "static")
    filename = "regolamento.pdf"
    return send_from_directory(directory, filename, as_attachment=True)

if __name__ == "__main__":
    # Specificare host per Render
    app.run(host="0.0.0.0", port=8080, debug=True)
