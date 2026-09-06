"""
Isolamento transazionale per i test che esercitano percorsi di scrittura.

Il problema: le route scrivono sul database e fanno commit. Girando contro un
database vero, un test lascerebbe dietro di se' giocatori svincolati, crediti
spostati e prestiti attivati.

La soluzione: una sola connessione dedicata, con una transazione aperta per
tutta la durata del test e annullata alla fine. Perche' la fedelta' resti alta,
i confini di transazione delle route vengono emulati con i savepoint invece di
essere ignorati:

    conn.commit()    ->  RELEASE SAVEPOINT + SAVEPOINT   (il lavoro resta, ma
                                                          dentro la transazione
                                                          esterna)
    conn.rollback()  ->  ROLLBACK TO SAVEPOINT           (annulla davvero cio'
                                                          che la route voleva
                                                          annullare)

Cosi' una route che fa rollback su errore si comporta esattamente come in
produzione, e il test puo' verificarlo, ma nulla sopravvive al test.
"""

import psycopg2
from psycopg2.extras import RealDictCursor

SAVEPOINT = "sp_test"


class ConnessioneIsolata:
    """Delega tutto alla connessione vera, tranne commit e rollback."""

    def __init__(self, conn):
        self._conn = conn
        self._apri_savepoint()

    def _apri_savepoint(self):
        with self._conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {SAVEPOINT};")

    def commit(self):
        with self._conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {SAVEPOINT};")
            cur.execute(f"SAVEPOINT {SAVEPOINT};")

    def rollback(self):
        with self._conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {SAVEPOINT};")

    # set_isolation_level dentro una transazione aperta darebbe errore, e non
    # serve: qui c'e' una sola connessione e nessuna concorrenza da simulare.
    def set_isolation_level(self, livello):
        pass

    def __getattr__(self, nome):
        return getattr(self._conn, nome)


def installa(monkeypatch, database_url):
    """Reindirizza il pool verso un'unica connessione isolata.

    Restituisce (proxy, chiudi): `chiudi` annulla tutto e chiude.
    """
    grezza = psycopg2.connect(database_url)
    grezza.autocommit = False
    proxy = ConnessioneIsolata(grezza)

    from app.core import db

    monkeypatch.setattr(db, "get_connection", lambda: proxy)
    monkeypatch.setattr(db, "release_connection", lambda conn=None, cur=None: cur.close() if cur else None)

    # I moduli hanno importato i nomi per valore: vanno sostituiti uno per uno.
    import importlib
    for nome in ("app.blueprints.rosa", "app.blueprints.mercato", "app.blueprints.prestiti",
                 "app.blueprints.aste", "app.blueprints.user", "app.blueprints.pubblico",
                 "app.blueprints.admin", "app.blueprints.vetrina", "app.telegram_utils"):
        modulo = importlib.import_module(nome)
        if hasattr(modulo, "get_connection"):
            monkeypatch.setattr(modulo, "get_connection", lambda: proxy, raising=False)
        if hasattr(modulo, "release_connection"):
            monkeypatch.setattr(modulo, "release_connection",
                                lambda conn=None, cur=None: cur.close() if cur else None, raising=False)

    def chiudi():
        try:
            grezza.rollback()
        finally:
            grezza.close()

    return proxy, chiudi


def cursore(proxy):
    return proxy.cursor(cursor_factory=RealDictCursor)
