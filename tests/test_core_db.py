"""
Test del ciclo di vita delle connessioni (app/core/db.py).

Sono di sola lettura sul database: nessuna tabella dell'applicazione viene
toccata. Il test centrale è quello sul ripristino dell'isolamento, che copre
una correzione di bug: prima, una route che alzava l'isolamento lo lasciava
appiccicato alla connessione restituita al pool.
"""

import psycopg2
import pytest
from psycopg2 import extensions as ext

from app.core.db import (ISOLAMENTO_DEFAULT, connessione, get_connection,
                         release_connection, transazione)

pytestmark = pytest.mark.db


class TestConnessione:
    def test_fornisce_connessione_e_cursore_funzionanti(self, app):
        with connessione() as (conn, cur):
            cur.execute("SELECT 1 AS uno;")
            assert cur.fetchone()["uno"] == 1

    def test_rilascia_al_pool_anche_in_caso_di_eccezione(self, app):
        """Se il rilascio non avvenisse, dopo maxconn (5) iterazioni il pool
        sarebbe esaurito e la sesta si bloccherebbe."""
        for _ in range(12):
            with pytest.raises(ValueError):
                with connessione() as (conn, cur):
                    cur.execute("SELECT 1;")
                    raise ValueError("errore simulato")

        with connessione() as (conn, cur):
            cur.execute("SELECT 1 AS uno;")
            assert cur.fetchone()["uno"] == 1

    def test_il_cursore_viene_chiuso_all_uscita(self, app):
        with connessione() as (conn, cur):
            pass
        assert cur.closed


class TestRipristinoIsolamento:
    """La correzione: l'isolamento non deve sopravvivere al rilascio."""

    def test_isolamento_alzato_non_sopravvive_al_rilascio(self, app):
        with connessione() as (conn, cur):
            conn.set_isolation_level(ext.ISOLATION_LEVEL_SERIALIZABLE)
            assert conn.isolation_level == ext.ISOLATION_LEVEL_SERIALIZABLE
            identita = id(conn)

        # Stessa connessione ripresa dal pool: deve essere tornata al default.
        with connessione() as (conn2, cur2):
            if id(conn2) == identita:
                assert conn2.isolation_level == ISOLAMENTO_DEFAULT

    def test_parametro_isolamento_viene_applicato(self, app):
        with connessione(isolamento=ext.ISOLATION_LEVEL_REPEATABLE_READ) as (conn, cur):
            assert conn.isolation_level == ext.ISOLATION_LEVEL_REPEATABLE_READ

    def test_dopo_il_rilascio_il_livello_effettivo_e_read_committed(self, app):
        with connessione(isolamento=ext.ISOLATION_LEVEL_SERIALIZABLE) as (conn, cur):
            identita = id(conn)

        with connessione() as (conn2, cur2):
            if id(conn2) != identita:
                pytest.skip("Il pool ha restituito una connessione diversa.")
            cur2.execute("SHOW transaction_isolation;")
            assert cur2.fetchone()["transaction_isolation"] == "read committed"


class TestTransazione:
    def test_propaga_l_eccezione(self, app):
        with pytest.raises(ValueError):
            with transazione() as (conn, cur):
                cur.execute("SELECT 1;")
                raise ValueError("errore simulato")

    def test_dopo_un_errore_la_connessione_torna_utilizzabile(self, app):
        """Senza il rollback, la connessione resterebbe in stato di transazione
        abortita e ogni query successiva fallirebbe con InFailedSqlTransaction."""
        with pytest.raises(psycopg2.Error):
            with transazione() as (conn, cur):
                cur.execute("SELECT * FROM tabella_che_non_esiste;")

        with connessione() as (conn, cur):
            cur.execute("SELECT 1 AS uno;")
            assert cur.fetchone()["uno"] == 1

    def test_committa_all_uscita_pulita(self, app):
        """Su una tabella temporanea, quindi senza toccare dati reali: la temp
        table è visibile solo a questa connessione e sparisce alla chiusura."""
        with transazione() as (conn, cur):
            cur.execute("CREATE TEMP TABLE prova_commit (v int) ON COMMIT DROP;")
            cur.execute("INSERT INTO prova_commit VALUES (42);")
            cur.execute("SELECT v FROM prova_commit;")
            assert cur.fetchone()["v"] == 42
        # ON COMMIT DROP: se il commit è avvenuto, la tabella non esiste più.
        with connessione() as (conn, cur):
            cur.execute("SELECT to_regclass('pg_temp.prova_commit') AS t;")
            assert cur.fetchone()["t"] is None


class TestReleaseConnection:
    def test_tollera_argomenti_nulli(self, app):
        release_connection(None, None)
        release_connection()

    def test_rilascio_esplicito_non_lascia_transazioni_aperte(self, app):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        assert conn.info.transaction_status == ext.TRANSACTION_STATUS_INTRANS
        release_connection(conn, cur)
        assert conn.info.transaction_status == ext.TRANSACTION_STATUS_IDLE
