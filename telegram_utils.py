import requests
import os
import psycopg2
import json
from flask import current_app
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from db import get_connection, release_connection

env_path = os.path.join(os.path.dirname(__file__), '.env')

load_dotenv(dotenv_path=env_path)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ Token non trovato nel file .env")
    exit()

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"




def asta_rilanciata(conn, id_asta, squadra_da_notificare):

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Recupero info per scrivere il messaggio
        cur.execute('''
                    SELECT g.nome, a.squadra_vincente, a.ultima_offerta
                    FROM asta a
                    JOIN giocatore g
                        ON a.giocatore = g.id
                    WHERE a.id = %s;
        ''', (id_asta,))
        info_asta = cur.fetchone()

        if not info_asta:
            print(f"Nessuna asta trovata con id {id_asta}")
            return

        giocatore = info_asta['nome']
        squadra_che_ha_rilanciato = info_asta['squadra_vincente']
        ultima_offerta = info_asta['ultima_offerta']

        text_to_send = (
            f"🏷️ ASTA: {giocatore}\n"
            f"La squadra {squadra_che_ha_rilanciato} ha rilanciato la tua offerta!\n"
            f"💰 Offerta attuale: {ultima_offerta} crediti."
        )

        send_message(squadra_da_notificare, text_to_send)

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)



def asta_iniziata(id_asta):
    print("Messaggio intercettato correttamente da supabase!")
    
            


















def send_message(nome_squadra, text_to_send):

    # Recupero degli id telegram
    try:
        IDS_TELEGRAM = current_app.config.get('SQUADRE_TELEGRAM_IDS', {})
        CHAT_IDS = IDS_TELEGRAM.get(nome_squadra, [])

        if not CHAT_IDS:
            print(f"⚠️ Attenzione: Nessun ID trovato in cache per la squadra '{nome_squadra}'.")
            return
        
    except Exception as e:
        print(f"❌ Errore critico di accesso alla cache: {e}")
        return

    # Fase di invio dei messaggi
    for chat_id in CHAT_IDS:
        payload = {"chat_id": chat_id, "text": text_to_send}

        try:
            r = requests.post(url, json=payload)
            if r.status_code == 200:
                print(f"✅ Messaggio inviato a {chat_id}")
            else:
                print(f"❌ Errore per {chat_id}: {r.text}")

        except requests.exceptions.RequestException as e:
            print(f"❌ Errore di Rete per {chat_id}: {e}")

    return
        




def get_all_telegram_ids():

    conn = None
    cur = None

    SQUADRE_IDS = {}

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT nome, id_telegram
                    FROM squadra
                    WHERE nome <> 'Svincolato';
        ''')
        squadre_raw = cur.fetchall()
       
        for s in squadre_raw:
            nome_squadra = s['nome']
            telegram_ids = s['id_telegram']

            if nome_squadra and isinstance(telegram_ids, list):
                SQUADRE_IDS[nome_squadra] = telegram_ids
            elif nome_squadra:
                 # Includi la squadra anche se l'array è NULL (vuoto) nel DB
                 SQUADRE_IDS[nome_squadra] = []

        print("✅ Inizializzato dizionario ID telegram")
        return SQUADRE_IDS

    except Exception as e:
        print(f"❌ Errore critico nel fetching della mappa ID: {e}")
        return {}

    finally:
        release_connection(conn, cur)

        
