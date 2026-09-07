"""
Il connection pool deve sopravvivere a un fork.

Nasce da un guasto in produzione: con gunicorn avviato con --preload
l'applicazione viene costruita una volta sola nel processo padre e i worker
nascono da un fork, ereditando le connessioni gia' aperte. Una connessione SSL
non sopravvive al fork: due processi che scrivono sulla stessa socket corrompono
il flusso a vicenda.

Il sintomo non e' un errore di connessione riconoscibile, ma query normali che
falliscono con "SSL error: bad record mac" oppure "SSL SYSCALL error: EOF
detected" - e nel caso del listone una pagina servita vuota con stato 200.
"""

import os

import pytest

pytestmark = pytest.mark.db


def _figlio_esegue_query(numero_query=6):
    """Esegue query in un processo figlio e riporta l'esito al padre.

    Il risultato passa da una pipe perche' un assert nel figlio non
    raggiungerebbe il processo di test.
    """
    from app.core import db

    lettura, scrittura = os.pipe()
    if os.fork() == 0:
        os.close(lettura)
        esito = "OK"
        try:
            for _ in range(numero_query):
                conn = db.get_connection()
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
                    cur.fetchone()
                db.release_connection(conn)
        except BaseException as e:
            esito = f"{type(e).__name__}: {e}"
        os.write(scrittura, esito.encode()[:400])
        os._exit(0)

    os.close(scrittura)
    os.wait()
    messaggio = os.read(lettura, 4096).decode()
    os.close(lettura)
    return messaggio


class TestPoolDopoFork:
    def test_un_processo_figlio_puo_usare_il_database(self, app):
        """Con il pool ereditato e non ricostruito, questa query fallisce con un
        errore SSL invece di restituire un risultato."""
        assert _figlio_esegue_query() == "OK"

    def test_piu_figli_in_parallelo_non_si_corrompono_a_vicenda(self, app):
        """Il caso reale: due worker gunicorn che servono richieste insieme."""
        esiti = [_figlio_esegue_query(4) for _ in range(3)]
        assert esiti == ["OK", "OK", "OK"], f"esiti: {esiti}"

    def test_il_padre_continua_a_funzionare_dopo_i_fork(self, app):
        """Le connessioni ereditate vengono abbandonate senza chiuderle: una
        close() manderebbe un messaggio di chiusura TLS sulla socket condivisa e
        romperebbe il processo padre, che la sta usando legittimamente."""
        _figlio_esegue_query(3)

        from app.core.db import connessione
        with connessione() as (conn, cur):
            cur.execute("SELECT 1 AS uno;")
            assert cur.fetchone()["uno"] == 1

    def test_il_pool_registra_il_processo_che_lo_ha_creato(self, app):
        from app.core import db
        assert db._pid_pool == os.getpid()
