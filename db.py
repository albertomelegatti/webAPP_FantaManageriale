import os
import psycopg2
import time
from psycopg2.extras import DictCursor
from psycopg2 import OperationalError
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():

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

    #return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.DictCursor)