from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scarica-regolamento")
def scarica_regolamento():
    directory = os.path.join(app.root_path, "static")
    filename = "Regolamento_Fantacalcio_Manageriale.pdf"
    return send_from_directory(directory, filename, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)

