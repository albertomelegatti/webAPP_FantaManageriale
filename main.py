import os
from flask import Flask, render_template, send_from_directory

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scarica-regolamento")
def scarica_regolamento():
    directory = os.path.join(app.root_path, "static")
    filename = "regolamento.pdf"
    return send_from_directory(directory, filename, as_attachment=True)

# Rotta per login admin
@app.route("/login-admin")
def login_admin():
    return render_template("adminLogin.html")

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

if __name__ == "__main__":
    app.run(debug=True)
