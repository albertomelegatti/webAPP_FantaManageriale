import os
import psycopg2
import time
from psycopg2.extras import RealDictCursor
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
        return pool

    if not DATABASE_URL:
        raise ValueError("Variabile d'ambiente DATABASE_URL non trovata")

    result = urlparse(DATABASE_URL)

    params = {
        "user": result.username,
        "password": result.password,
        "host": result.hostname,
        "port": result.port,
        "dbname": "postgres"
    }

    try:
        pool = psycopg2.pool.ThreadedConnectionPool(
            minconn = 1,
            maxconn = 5,
            **params
        )
        print("✅ Pool di connessioni Supabase inizializzato con successo!")
        return pool
    except psycopg2.Error as e:
        print(f"❌ Errore critico nell'inizializzazione del pool: {e}")
        pool = None
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
    
    max_retries = 5
    cooldown = 2
    global pool

    if pool is None:
        raise Exception("Connection pool non inizializzato. Chiama init_pool() prima.")
    
    retries = 0

    while retries < max_retries:
        try:
            conn = pool.getconn()
            conn.rollback()
            conn.autocommit = False
            # Verifica che la connessione sia ancora viva
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            return conn
        
        except OperationalError as e:
            retries += 1
            print(f"[DB] Tentativo {retries}/{max_retries} fallito: {e}")

            if retries < max_retries:
                print(f"[DB] Ritento tra {cooldown} secondi...")
                time.sleep(cooldown)

            else:
                print("[DB] ❌ Impossibile connettersi al database dopo ripetuti tentativi.")
                raise


#def get_connection():
    #return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)


def release_connection(conn=None, cur=None):
    
    # Rilascia la connessione al pool e chiude il cursore.
    # Gestisce gracefully i casi in cui conn o cur non sono validi.
    
    global pool
    
    # 1. Chiudi sempre il cursore per primo (se presente)
    if cur:
        try:
            cur.close()
        except Exception as e:
            print(f"⚠️ Errore nella chiusura del cursore: {e}")
    
    # 2. Se non c'è pool, non possiamo fare nulla
    if not pool:
        print("⚠️ Pool non disponibile, impossibile rilasciare la connessione")
        if conn:
            try:
                conn.close()  # Chiudi direttamente
            except Exception:
                pass
        return
    
    # 3. Rilascia la connessione al pool
    if not conn:
        return
    
    try:
        # Annulla transazioni aperte (rollback di sicurezza)
        if not conn.closed:
            try:
                conn.rollback()
            except Exception as e:
                print(f"⚠️ Errore nel rollback: {e}")
            
            # Rimetti la connessione nel pool
            try:
                pool.putconn(conn, close=False)
            except Exception as e:
                print(f"⚠️ Errore nel rilascio al pool: {e}")
                # Se fallisce il putconn, chiudi direttamente
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            # Connessione già chiusa
            print("⚠️ Connessione già chiusa, non rimessa nel pool")
            
    except Exception as e:
        print(f"⚠️ Errore imprevisto in release_connection: {e}")
        try:
            conn.close()
        except Exception:
            pass




def check_connection():
    #Tenta di ottenere una connessione dal pool ed esegue una query di test.
    #Restituisce True in caso di successo, False altrimenti.
    conn = None
    try:
        # 1. Ottiene la connessione dal pool
        conn = get_connection()
        
        # 2. Esegue una query banale (SELECT 1) per testare la validità
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        
        print("✅ Controllo di connessione riuscito. Pool OK.")
        return True
        
    except psycopg2.OperationalError as e:
        # Cattura gli errori operativi (timeout, rifiuto, SSL EOF)
        print(f"❌ ERRORE CRITICO DI CONNESSIONE: {e}")
        return False
        
    except Exception as e:
        # Cattura altri errori generici (es. pool non inizializzato)
        print(f"❌ Errore generico durante il controllo di connessione: {e}")
        return False
        
    finally:
        # 3. Rilascia la connessione, SEMPRE
        if conn:
            release_connection(conn)





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
