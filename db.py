import os
from psycopg2.extras import DictCursor
from psycopg2 import OperationalError
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
pool = None


def init_pool():
    #Inizializza il connection pool (solo una volta)
    global pool
    if pool is None:
        pool = SimpleConnectionPool(
            minconn=1,
            maxconn=5,
            dsn=DATABASE_URL,
            cursor_factory=DictCursor
        )
        print("✅ Connection pool inizializzato")
    return pool


def log_pool_status(action):
    #Stampa lo stato corrente del pool
    global pool
    if pool:
        used = len(pool._used)
        free = len(pool._pool)
        print(f"📊 [POOL STATUS] {action} | Attive: {used} | Libere: {free}")
    else:
        print("⚠️ Pool non inizializzato.")


def get_connection():
    #Ottiene una connessione attiva dal pool
    global pool
    if pool is None:
        raise Exception("Connection pool non inizializzato. Chiama init_pool() prima.")

    conn = pool.getconn()
    log_pool_status("Connessione ottenuta")

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")  # test connessione
    except OperationalError:
        print("⚠️ Connessione scaduta, ne creo una nuova...")
        pool.putconn(conn, close=True)
        conn = pool.getconn()

    return conn


def release_connection(conn):
    #Rilascia la connessione al pool
    global pool
    if pool and conn:
        try:
            pool.putconn(conn)
            log_pool_status("Connessione rilasciata")
        except Exception as e:
            print(f"⚠️ Errore nel rilascio connessione: {e}")



def print_pool_status():
    global pool
    if pool is None:
        print("❌ Connection pool non inizializzato")
        return
    
    used = len(pool._used) if hasattr(pool, "_used") else "?"
    free = len(pool._pool) if hasattr(pool, "_pool") else "?"
    print(f"📊 Pool status → attive: {used}, libere: {free}, totali: {used + free if used != '?' and free != '?' else '?'}")


def keep_awake():
    
    #Funzione che mantiene viva la connessione al database.
    #Esegue una semplice query SELECT 1.
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")  # Query minimale
        cur.close()
    except Exception as e:
        print("⚠️ Errore in keep_awake:", e)
    finally:
        if conn:
            release_connection(conn)
