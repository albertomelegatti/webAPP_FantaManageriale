import os
from flask import Flask, render_template, send_from_directory

app = Flask(__name__)

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "1234"

@app.route("/")
def home():
    return render_template("index.html")


# Rotta per login admin
@app.route("/login-admin", methods=["GET", "POST"])
def login_admin():
    username = request.form.get("username")
    password = request.form.get("password")

    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        return render_template("adminLogin.html")
    else:
        return "<h2>Credenziali non valide. Riprova.</h2>"
    

# Rotta per login squadre
@app.route("/login-squadre")
def login_squadre():
    return render_template("squadre.html")

@app.route("/rose")
def rose():
    return "<h2>Sezione Rose (in costruzione)</h2>"

@app.route("/stadi")
def stadi():
    return "<h2>Sezione Stadi (in costruzione)</h2>"

@app.route("/prestiti")
def prestiti():
    return "<h2>Sezione Prestiti (in costruzione)</h2>"

@app.route("/scarica-regolamento")
def scarica_regolamento():
    directory = os.path.join(app.root_path, "static")
    filename = "regolamento.pdf"
    return send_from_directory(directory, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
