"""
Shim di compatibilità per l'entrypoint WSGI.

L'entrypoint vero è `wsgi.py`, ed è quello indicato dal Procfile. Questo modulo
esiste perché il comando di avvio configurato nella dashboard di Render è
`gunicorn main:app`, che ha la precedenza sul Procfile: dopo lo spostamento
delle route nel package `app/` il deploy falliva con
"ModuleNotFoundError: No module named 'main'".

Finché il comando su Render non viene allineato al Procfile, questo file tiene
in piedi entrambe le forme (`main:app` e `wsgi:app`). Una volta allineato può
essere eliminato.
"""

from app import create_app

app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
