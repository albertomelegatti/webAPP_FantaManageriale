"""
Accesso al database: connection pool e gestione del ciclo di vita delle
connessioni.

L'interfaccia da usare nel codice nuovo è il context manager `connessione()`
(oppure `transazione()` quando serve il commit automatico). `get_connection()` e
`release_connection()` restano pubbliche perché sono ancora usate direttamente
in qualche punto, ma non vanno usate in codice nuovo: dimenticare il `finally`
significa perdere una connessione dal pool.
"""

import os
import threading
import time
from contextlib import contextmanager
from urllib.parse import urlparse

import psycopg2
import psycopg2.pool
from dotenv import load_dotenv
from psycopg2 import OperationalError, sql
from psycopg2.extras import RealDictCursor

from app.core.logging import get_logger

logger = get_logger(__name__)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
pool = None

# Isolamento a cui ogni connessione viene riportata prima di tornare nel pool.
#
# Senza questo ripristino, una route che alza l'isolamento (REPEATABLE READ o
# SERIALIZABLE) lo lascia appiccicato alla connessione, e la richiesta successiva
# che la preleva lo eredita senza saperlo — con SERIALIZABLE significa
# SerializationFailure sporadici in route che non li gestiscono.
#
# Il valore è ISOLATION_LEVEL_DEFAULT, che in psycopg2 vale None: riporta la
# connessione a "usa il default del server" (qui: read committed), cioè
# esattamente lo stato di una connessione appena aperta. Ripristinare None
# invece di un livello esplicito e' piu' fedele: non pinna un valore che il
# server potrebbe avere configurato diversamente.
ISOLAMENTO_DEFAULT = psycopg2.extensions.ISOLATION_LEVEL_DEFAULT

# Una connessione rilasciata da poco è quasi certamente ancora viva: rivalidarla
# con un SELECT 1 costerebbe un round-trip verso Supabase a ogni checkout, cioè
# su ogni richiesta. Sopra questa soglia di inattività la validazione viene
# invece eseguita, perché il server può aver chiuso una connessione idle.
SECONDI_VALIDITA_PRESUNTA = 60

_ultimo_rilascio = {}
_ultimo_rilascio_lock = threading.Lock()


def init_pool():
    """Inizializza il connection pool (solo una volta)."""
    global pool
    if pool is not None:
        logger.info("Il pool è già inizializzato.")
        return pool

    if not DATABASE_URL:
        raise ValueError("Variabile d'ambiente DATABASE_URL non trovata")

    result = urlparse(DATABASE_URL)

    params = {
        "user": result.username,
        "password": result.password,
        "host": result.hostname,
        "port": result.port,
        "dbname": "postgres",
        "connect_timeout": 10,
    }

    try:
        pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=5, **params)
        logger.info("✅ Pool di connessioni Supabase inizializzato con successo!")
        resync_sequences()
        return pool
    except psycopg2.Error as e:
        logger.exception("❌ Errore critico nell'inizializzazione del pool")
        pool = None
        raise


def resync_sequences():
    """Riallinea le sequence di tutte le tabelle al MAX(id) attualmente presente.

    Serve perché import/restore manuali sul DB possono inserire righe con id
    espliciti senza far avanzare la sequence, causando poi collisioni di chiave
    primaria sui successivi INSERT dell'app. Viene eseguito ad ogni avvio così
    il problema si corregge da solo, senza interventi manuali sul DB.
    """
    try:
        with transazione() as (conn, cur):
            cur.execute('''
                DO $$
                DECLARE
                    r RECORD;
                BEGIN
                    FOR r IN
                        SELECT
                            t.relname AS table_name,
                            a.attname AS column_name,
                            pg_get_serial_sequence(t.relname, a.attname) AS seq_name
                        FROM pg_class t
                        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum > 0 AND NOT a.attisdropped
                        WHERE t.relkind = 'r'
                          AND t.relnamespace = 'public'::regnamespace
                          AND pg_get_serial_sequence(t.relname, a.attname) IS NOT NULL
                    LOOP
                        EXECUTE format(
                            'SELECT setval(%L, COALESCE((SELECT MAX(%I) FROM %I), 1))',
                            r.seq_name, r.column_name, r.table_name
                        );
                    END LOOP;
                END $$;
            ''')
        logger.info("✅ Sequence delle tabelle riallineate con successo.")
    except Exception as e:
        logger.exception("⚠️ Errore durante il riallineamento delle sequence")


def resync_sequence(conn, table_name, column_name="id"):
    """Riallinea la sequence di una singola tabella al MAX(colonna) attuale,
    usando la connessione già aperta dal chiamante (nessun nuovo checkout dal pool).

    Pensata per essere invocata a runtime, dopo un errore di chiave duplicata,
    così il problema si autocorregge anche senza riavviare il worker (es. su Render,
    dove i processi restano attivi a lungo senza restart).
    """
    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("SELECT setval(pg_get_serial_sequence(%s, %s), COALESCE((SELECT MAX({}) FROM {}), 1))").format(
                sql.Identifier(column_name), sql.Identifier(table_name)
            ),
            (table_name, column_name)
        )
    conn.commit()


def _va_validata(conn):
    """True se la connessione è rimasta inattiva abbastanza a lungo da poter
    essere stata chiusa dal server."""
    with _ultimo_rilascio_lock:
        rilasciata_a = _ultimo_rilascio.get(id(conn))
    if rilasciata_a is None:
        return True
    return (time.monotonic() - rilasciata_a) > SECONDI_VALIDITA_PRESUNTA


def get_connection():
    """Preleva una connessione dal pool, riprovando se il database non risponde.

    Da preferire il context manager `connessione()`: chi chiama questa funzione
    è responsabile di invocare `release_connection()` in un `finally`.
    """
    max_retries = 5
    cooldown = 2

    if pool is None:
        raise Exception("Connection pool non inizializzato. Chiama init_pool() prima.")

    retries = 0
    while retries < max_retries:
        try:
            conn = pool.getconn()
            conn.autocommit = False

            # Validazione solo se la connessione è stata ferma a lungo: su una
            # appena rilasciata sarebbe un round-trip sprecato a ogni richiesta.
            if _va_validata(conn):
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")

            return conn

        except OperationalError as e:
            retries += 1
            logger.warning("[DB] Tentativo %s/%s fallito: %s", retries, max_retries, e)

            if retries < max_retries:
                logger.info("[DB] Ritento tra %s secondi...", cooldown)
                time.sleep(cooldown)
            else:
                logger.error("[DB] Impossibile connettersi al database dopo ripetuti tentativi.")
                raise


def release_connection(conn=None, cur=None):
    """Chiude il cursore e restituisce la connessione al pool.

    Prima di restituirla esegue rollback e ripristina l'isolamento di default,
    così la richiesta successiva la trova in uno stato pulito e prevedibile.
    """
    if not pool or not conn:
        return

    if cur:
        try:
            cur.close()
        except Exception as e:
            logger.exception("⚠️ Impossibile chiudere il cursore")

    if conn.closed:
        return

    try:
        conn.rollback()
        if conn.isolation_level != ISOLAMENTO_DEFAULT:
            conn.set_isolation_level(ISOLAMENTO_DEFAULT)
    except Exception as e:
        # Connessione in stato incerto: non va rimessa nel pool.
        logger.exception("⚠️ Errore nel ripulire la connessione, viene scartata")
        _dimentica(conn)
        try:
            pool.putconn(conn, close=True)
        except Exception:
            pass
        return

    with _ultimo_rilascio_lock:
        _ultimo_rilascio[id(conn)] = time.monotonic()

    try:
        pool.putconn(conn, close=False)
    except Exception as e:
        logger.exception("⚠️ Errore durante putconn")
        _dimentica(conn)
        try:
            conn.close()
        except Exception:
            pass


def _dimentica(conn):
    with _ultimo_rilascio_lock:
        _ultimo_rilascio.pop(id(conn), None)


@contextmanager
def connessione(*, isolamento=None):
    """Connessione e cursore dal pool, con rilascio garantito.

    Non committa: il chiamante resta responsabile dei propri `conn.commit()`,
    esattamente come con get_connection/release_connection. È la forma da usare
    quando i commit sono più di uno o sono condizionali.

        with connessione() as (conn, cur):
            cur.execute("SELECT ...")
    """
    conn = get_connection()
    cur = None
    try:
        if isolamento is not None:
            conn.set_isolation_level(isolamento)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        yield conn, cur
    finally:
        release_connection(conn, cur)


@contextmanager
def transazione(*, isolamento=None):
    """Come `connessione()`, ma committa all'uscita pulita e fa rollback se
    viene sollevata un'eccezione.

        with transazione() as (conn, cur):
            cur.execute("UPDATE ...")
    """
    with connessione(isolamento=isolamento) as (conn, cur):
        try:
            yield conn, cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
