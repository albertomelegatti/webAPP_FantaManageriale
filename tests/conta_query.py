"""
Contatore di query, per dimostrare che una pagina non interroga il database un
numero di volte proporzionale alle righe che mostra.

Avvolge la connessione del pool e registra ogni execute. Serve a rendere le
regressioni di tipo N+1 visibili in un test invece che solo in produzione sotto
carico.
"""

from contextlib import contextmanager


class _CursoreContatore:
    def __init__(self, cursore, registro):
        self._cursore = cursore
        self._registro = registro

    def execute(self, query, vars=None):
        self._registro.append(" ".join(str(query).split())[:120])
        return self._cursore.execute(query, vars)

    def __getattr__(self, nome):
        return getattr(self._cursore, nome)

    def __enter__(self):
        self._cursore.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursore.__exit__(*args)


class _ConnessioneContatrice:
    def __init__(self, connessione, registro):
        self._connessione = connessione
        self._registro = registro
        self.checkout = 0

    def cursor(self, *args, **kwargs):
        return _CursoreContatore(self._connessione.cursor(*args, **kwargs), self._registro)

    def __getattr__(self, nome):
        return getattr(self._connessione, nome)


class Registro(list):
    """Elenco delle query eseguite, piu' il numero di connessioni prelevate dal
    pool: una pagina che ne preleva piu' di una per richiesta e' un segnale di
    checkout annidati."""

    def __init__(self):
        super().__init__()
        self.checkout = []


@contextmanager
def conta_query(monkeypatch):
    """Registra le query eseguite nel blocco. Restituisce il registro, che si
    puo' interrogare dopo l'uscita."""
    from app.core import db

    registro = Registro()
    originale_get = db.get_connection
    originale_release = db.release_connection
    def get_connection_contata():
        conn = originale_get()
        registro.checkout.append(conn)
        return _ConnessioneContatrice(conn, registro)

    def release_contata(conn=None, cur=None):
        vera = getattr(conn, "_connessione", conn)
        cur_vero = getattr(cur, "_cursore", cur)
        return originale_release(vera, cur_vero)

    monkeypatch.setattr(db, "get_connection", get_connection_contata)
    monkeypatch.setattr(db, "release_connection", release_contata)
    yield registro
