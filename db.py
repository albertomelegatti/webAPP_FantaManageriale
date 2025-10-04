import os
#import psycopg2
#import time
from psycopg2.extras import DictCursor
from psycopg2 import OperationalError
from psycopg2.pool import SimpleConnectionPool
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
pool = None


def init_pool():
    #Inizializza il connection pool (solo la prima volta)
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
    #Ottiene una connessione attiva dal pool
    global pool
    if pool is None:
        raise Exception("Connection pool non inizializzato. Chiama init_pool() prima.")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")  # test connessione
    except OperationalError:
        print("⚠️ Connessione scaduta, ne creo una nuova...")
        # sostituisci la connessione corrotta con una nuova
        pool.putconn(conn, close=True)
        conn = pool.getconn()
    return conn



def release_connection(conn):
    #Rilascia la connessione al pool
    global pool
    if pool and conn:
        pool.putconn(conn)





    '''
    max_retries = 10
    delay = 2
    
    retries = 0
    while retries < max_retries:
        try:
            conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)
            # test connessione
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
            return conn
        except OperationalError as e:
            print(f"Connessione fallita, tentativo {retries+1}/{max_retries}: {e}")
            retries += 1
            time.sleep(delay)
    raise OperationalError(f"Impossibile connettersi al database dopo {max_retries} tentativi")
    '''
    #return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)