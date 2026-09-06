"""
Configurazione del logging.

Sostituisce i `print` sparsi nel codice. La differenza che conta non è
stilistica: `print` di un'eccezione ne stampa solo il messaggio e butta via lo
stack trace, quindi dai log di produzione non si risale mai al punto in cui
l'errore è nato. `logger.exception()` lo conserva.

Il formato è a riga singola con timestamp, livello e modulo, così resta
leggibile nella console di Render senza bisogno di strumenti esterni.
"""

import logging
import os
import sys

FORMATO = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"


def configura_logging(livello=None):
    """Configura il logger radice. Idempotente: chiamarla più volte non
    duplica gli handler (succederebbe nei test, dove create_app gira più volte).
    """
    if livello is None:
        livello = os.getenv("LOG_LEVEL", "INFO").upper()

    radice = logging.getLogger()
    radice.setLevel(livello)

    for handler in radice.handlers:
        if getattr(handler, "_configurato_da_noi", False):
            handler.setLevel(livello)
            return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(FORMATO, datefmt=FORMATO_DATA))
    handler.setLevel(livello)
    handler._configurato_da_noi = True
    radice.addHandler(handler)

    # Le richieste HTTP le logga già gunicorn: senza questo, ogni richiesta
    # comparirebbe due volte.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def get_logger(nome):
    """Logger per modulo. Da usare come `logger = get_logger(__name__)`."""
    return logging.getLogger(nome)
