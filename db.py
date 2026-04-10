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
        "dbname": "postgres",
        "connect_timeout": 10
    }

    try:
        pool = psycopg2.pool.ThreadedConnectionPool(
            minconn = 5,
            maxconn = 50,
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
    
    if not pool:
        print("⚠️ Pool non inizializzato.")


def get_connection():
    
    max_retries = 5
    cooldown = 2
    global pool

    if pool is None:
        raise Exception("Connection pool non inizializzato. Chiama init_pool() prima.")
    
    retries = 0
    log_pool_status("BEFORE_GETCONN")

    while retries < max_retries:
        try:
            conn = pool.getconn()
            conn.rollback()
            conn.autocommit = False
            # Verifica che la connessione sia ancora viva
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
            log_pool_status("CONNECTION_OK")
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

    global pool
    if not pool or not conn:
        return

    try:
        # Chiudi il cursore per primo
        if cur:
            try:
                cur.close()
            except Exception as e:
                print(f"⚠️ Impossibile chiudere il cursore: {e}")

        # Poi gestisci la connessione
        try:
            if not conn.closed:
                # Prova a fare rollback prima di restituire al pool
                try:
                    conn.rollback()
                    print(f"[DB] Connection rolled back successfully")
                except Exception as e:
                    print(f"⚠️ Errore durante rollback: {e}")
                    # Prova comunque a restituire la connessione
                
                # Restituisci la connessione al pool
                try:
                    pool.putconn(conn, close=False)
                except Exception as e:
                    print(f"⚠️ Errore durante putconn: {e}")
                    # Chiudi la connessione se non riesci a metterla nel pool
                    try:
                        conn.close()
                    except Exception:
                        pass
        except Exception as e:
            print(f"⚠️ Errore durante il rilascio connessione al pool: {e}")
            try:
                conn.close()
            except Exception:
                pass

    except Exception as e:
        print(f"⚠️ Errore imprevisto durante release_connection: {e}")
        try:
            if conn and not conn.closed:
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
    
    # Funzione che mantiene la web app e il database attivi.
    # Effettua una query di test e rilascia subito la connessione.
    
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


class DatabaseConnection:
    # Context manager per gestire connessioni al database in modo sicuro
    
    def __init__(self):
        self.conn = None
        self.cur = None
    
    def __enter__(self):
        """Acquisisce una connessione dal pool"""
        self.conn = get_connection()
        self.cur = self.conn.cursor(cursor_factory=RealDictCursor)
        return self.conn, self.cur
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Rilascia la connessione al pool"""
        try:
            if exc_type:
                print(f"[DatabaseConnection] Exception occurred: {exc_type.__name__}: {exc_val}")
                if self.conn and not self.conn.closed:
                    self.conn.rollback()
            elif self.conn and not self.conn.closed:
                self.conn.commit()
        except Exception as e:
            print(f"[DatabaseConnection] Error in exit: {e}")
            if self.conn and not self.conn.closed:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
        finally:
            release_connection(self.conn, self.cur)
        
        return False  # Propaga le eccezioni

