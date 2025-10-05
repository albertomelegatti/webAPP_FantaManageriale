import os
import psycopg2
from psycopg2.extras import DictCursor
from psycopg2 import OperationalError
from psycopg2.pool import SimpleConnectionPool, ThreadedConnectionPool
from dotenv import load_dotenv
from urllib.parse import urlparse

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
pool = None


def init_pool():
    #Inizializza il connection pool (solo una volta)
    
    global pool
    if pool is not None:
        print("Il pool è già inizializzato.")

    if not DATABASE_URL:
        raise ValueError("Variabile d'ambiente DATABASE_URL non trovata")

    result = urlparse(DATABASE_URL)

    params = {
        "user": result.username,
        "password": result.password,
        "host": result.hostname,
        "port": result.port,
        "dbname": "postgres",
        "application_name": "WebApp_Fanta",
        "sslmode": "require"
    }
    #print(params)

    try:
        pool = psycopg2.pool.ThreadedConnectionPool(
            minconn = 2,
            maxconn = 20,
            **params
        )
        print("✅ Pool di connessioni Supabase inizializzato con successo!")
    except psycopg2.Error as e:
        print(f"❌ Errore critico nell'inizializzazione del pool: {e}")
        raise


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

    return pool.getconn()

def release_connection(conn):
    #Rilascia la connessione al pool
    global pool
    if pool and conn:
        pool.putconn(conn)



def print_pool_status():
    global pool
    if pool is None:
        print("❌ Connection pool non inizializzato")
        return
    
    used = len(pool._used) if hasattr(pool, "_used") else "?"
    free = len(pool._pool) if hasattr(pool, "_pool") else "?"
    print(f"📊 Pool status → attive: {used}, libere: {free}, totali: {used + free if used != '?' and free != '?' else '?'}")


def keep_awake():
    """
    Funzione che mantiene la web app e il database attivi.
    Effettua una query di test e rilascia subito la connessione.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")  # semplice query di test
    except Exception as e:
        print("⚠️ Errore in keep_awake:", e)
    finally:
        if conn:
            release_connection(conn)
