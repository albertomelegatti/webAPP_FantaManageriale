import os
from flask import Flask, render_template, send_from_directory, request

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
    return render_template("rose.html")

@app.route("/squadra/nome_squadra>")
def mostra_rosa(nome_squadra):
    return render_template("rosa.html", nome_squadra=nome_squadra)

@app.route("/stadi")
def stadi():
    return "<h2>Sezione Stadi (in costruzione)</h2>"

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
