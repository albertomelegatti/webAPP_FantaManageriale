import threading
import time
import requests
from flask import Flask, render_template

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("index.html")

# Funzione che fa ping ogni 10 minuti
def keep_alive():
    while True:
        try:
            requests.get("https://webapp-fantamanageriale.onrender.com/")
        except:
            pass
        time.sleep(840)  # 600 secondi = 10 minuti

# Avvia il thread quando si lancia il server
threading.Thread(target=keep_alive, daemon=True).start()

if __name__ == "__main__":
    app.run(debug=True)
