"""
Entrypoint WSGI: è questo che gunicorn carica in produzione (vedi Procfile).

Sostituisce main.py, che costruiva l'app come effetto collaterale dell'import.
"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
