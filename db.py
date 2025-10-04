import os
import time
from psycopg2.extras import DictCursor
from psycopg2 import OperationalError
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
pool = None


def init_pool():
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


def get_connection():
    global pool
    
    if pool is None:
        raise Exception("Connection pool non inizializzato. Chiama init_pool() prima.")

    print_pool_status()
    
    conn = pool.getconn()
    try:
        if conn.closed != 0:  # 0 = aperta
            print("⚠️ Connessione chiusa nel pool, ne creo una nuova...")
            pool.putconn(conn, close=True)
            conn = pool._connect()

        else:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")  # test connessione
    except Exception as e:
        print(f"⚠️ Connessione non valida ({e}), ne creo una nuova...")
        pool.putconn(conn, close=True)
        conn = pool._connect()

    return conn



def release_connection(conn):
    global pool
    if pool and conn:
        try:
            pool.putconn(conn)
        except Exception as e:
            print(f"⚠️ Errore nel rilascio connessione: {e}. Provo a chiuderla.")
            try:
                conn.close()
            except Exception:
                pass


def print_pool_status():
    global pool
    if pool is None:
        print("❌ Connection pool non inizializzato")
        return
    
    used = len(pool._used) if hasattr(pool, "_used") else "?"
    free = len(pool._pool) if hasattr(pool, "_pool") else "?"
    print(f"📊 Pool status → attive: {used}, libere: {free}, totali: {used + free if used != '?' and free != '?' else '?'}")
