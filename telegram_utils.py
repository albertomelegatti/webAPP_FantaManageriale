import requests
import os
import time
import textwrap
import json
from flask import current_app
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from db import get_connection, release_connection
from user import format_giocatori, formatta_data

env_path = os.path.join(os.path.dirname(__file__), '.env')

load_dotenv(dotenv_path=env_path)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    print("❌ Token non trovato nel file .env")
    exit()

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"


def nuova_asta(conn, id_asta):

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT g.nome, a.squadra_vincente, a.tempo_fine_mostra_interesse
                    FROM asta a
                        JOIN giocatore g ON a.giocatore = g.id
                    WHERE a.id = %s;
        ''', (id_asta,))
        info_asta = cur.fetchone()

        if not info_asta:
            print(f"Nessuna asta trovata con id {id_asta}")
            return

        giocatore = info_asta['nome']
        squadra_vincente = info_asta['squadra_vincente']
        tempo_fine_mostra_interesse = formatta_data(info_asta['tempo_fine_mostra_interesse'])


        text_to_send = textwrap.dedent(f'''
            🏷️ ASTA: {giocatore}
            La squadra {squadra_vincente} ha iniziato un'asta!
            📆 Hai tempo per iscriverti fino a: {tempo_fine_mostra_interesse}.
        ''')

        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome NOT IN ('Svincolato', %s);
        ''', (squadra_vincente,))
        squadre_raw = cur.fetchall()
        squadre = [{"nome": s["nome"]} for s in squadre_raw]

        for s in squadre:
            print("Invio messaggio a ", s)
            send_message(nome_squadra=s['nome'], text_to_send=text_to_send)
            time.sleep(2)  # Delay per evitare spam

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)



def asta_rilanciata(conn, id_asta):

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Recupero info per scrivere il messaggio
        cur.execute('''
                    SELECT g.nome, a.squadra_vincente, a.ultima_offerta, a.partecipanti
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

        text_to_send = textwrap.dedent(f'''
            🏷️ ASTA: {giocatore}
            La squadra {squadra_che_ha_rilanciato} ha rilanciato l'offerta!
            💰 Offerta attuale: {ultima_offerta} crediti.
        ''')

        for partecipante in info_asta['partecipanti']:
            send_message(nome_squadra=partecipante, text_to_send=text_to_send)
            time.sleep(2)  # Delay per evitare spam

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)




def nuovo_scambio(conn, id_scambio):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT squadra_proponente, squadra_destinataria, giocatori_offerti, giocatori_richiesti, crediti_offerti, crediti_richiesti, messaggio
                    FROM scambio
                    WHERE id = %s;
        ''', (id_scambio,))
        info_scambio = cur.fetchone()

        if not info_scambio:
            print(f"Nessuno scambio trovato con id: {id_scambio}")
            return

        squadra_proponente = info_scambio['squadra_proponente']
        squadra_destinataria = info_scambio['squadra_destinataria']
        giocatori_offerti = format_giocatori(info_scambio['giocatori_offerti']) or []
        giocatori_richiesti = format_giocatori(info_scambio['giocatori_richiesti']) or []
        crediti_offerti = info_scambio['crediti_offerti'] or 0
        crediti_richiesti = info_scambio['crediti_richiesti'] or 0
        messaggio = info_scambio['messaggio'] or ""

        text_to_send = textwrap.dedent(f'''
            🟢 NUOVA PROPOSTA DI SCAMBIO
            La squadra {squadra_proponente} ti ha inviato una proposta di scambio

            ⚽ Offerta:
            {giocatori_offerti}
            💰 Crediti offerti: {crediti_offerti}

            ⚽ Richiesta:
            {giocatori_richiesti}
            💰 Crediti richiesti: {crediti_richiesti}

            ✉️ Messaggio: {messaggio}
        ''')

        send_message(nome_squadra=squadra_destinataria, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)




def scambio_risposta(conn, id_scambio, risposta):

    if not risposta or (risposta != "Accettato" and risposta != "Rifiutato"):
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT squadra_proponente, squadra_destinataria, giocatori_offerti, giocatori_richiesti, crediti_offerti, crediti_richiesti
                    FROM scambio
                    WHERE id = %s;
        ''', (id_scambio,))
        info_scambio = cur.fetchone()

        if not info_scambio:
            print(f"Nessuno scambio trovato con id: {id_scambio}")
            return

        squadra_proponente = info_scambio['squadra_proponente']
        squadra_destinataria = info_scambio['squadra_destinataria']
        giocatori_offerti = format_giocatori(info_scambio['giocatori_offerti']) or []
        giocatori_richiesti = format_giocatori(info_scambio['giocatori_richiesti']) or []
        crediti_offerti = info_scambio['crediti_offerti'] or 0
        crediti_richiesti = info_scambio['crediti_richiesti'] or 0

        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''
                SCAMBIO ACCETTATO
                La squadra {squadra_destinataria} ha accettato la tua offerta di scambio.

                ⚽ Offerta:
                {giocatori_offerti}
                💰 Crediti offerti: {crediti_offerti}

                ⚽ Richiesta:
                {giocatori_richiesti}
                💰 Crediti richiesti: {crediti_richiesti}
            ''')
        
        else:
            text_to_send = textwrap.dedent(f'''
                SCAMBIO RIFIUTATO
                La squadra {squadra_destinataria} ha rifiutato la tua offerta di scambio.

                ⚽ Offerta:
                {giocatori_offerti}
                💰 Crediti offerti: {crediti_offerti}

                ⚽ Richiesta:
                {giocatori_richiesti}
                💰 Crediti richiesti: {crediti_richiesti}
        ''')

        send_message(nome_squadra=squadra_proponente, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)






def nuovo_prestito(conn, id_prestito):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT p.giocatore, p.squadra_prestante, p.squadra_ricevente, p.data_fine
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.id = %s;
        ''', (id_prestito,))
        info_prestito = cur.fetchone()

        giocatore = info_prestito['nome']
        squadra_prestante = info_prestito['squadra_prestante']
        squadra_ricevente = info_prestito['squadra_ricevente']
        data_fine = formatta_data(info_prestito['data_fine'])

        text_to_send = textwrap.dedent(f'''
            🟢 NUOVA PROPOSTA DI PRESTITO
            La squadra {squadra_ricevente} ti ha inviato una proposta di prestito:
            ⚽ Giocatore: {giocatore}
            📆 Fino a: {data_fine}
        ''')

        send_message(nome_squadra=squadra_prestante, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)





def prestito_risposta(conn, id_prestito, risposta):

    if not risposta or (risposta != "Accettato" and risposta != "Rifiutato"):
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT p.giocatore, p.squadra_prestante, p.squadra_ricevente, p.data_fine
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.id = %s;
        ''', (id_prestito,))
        info_prestito = cur.fetchone()

        giocatore = info_prestito['nome']
        squadra_prestante = info_prestito['squadra_prestante']
        squadra_ricevente = info_prestito['squadra_ricevente']
        data_fine = formatta_data(info_prestito['data_fine'])

        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''
                PRESTITO ACCETTATO
                La squadra {squadra_prestante} ha accettato la tua richiesta di prestito:
                ⚽ Giocatore: {giocatore}
                📆 Fino a: {data_fine}
            ''')
        else:
            text_to_send = textwrap.dedent(f'''
                PRESTITO RIFIUTATO
                La squadra {squadra_prestante} ha rifiutato la tua richiesta di prestito:
                ⚽ Giocatore: {giocatore}
                📆 Fino a: {data_fine}
            ''')

        send_message(nome_squadra=squadra_ricevente, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)




def richiesta_terminazione_prestito(conn, id_prestito):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT p.giocatore, p.squadra_prestante, p.squadra_ricevente, p.data_fine, p.richiedente_terminazione
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.id = %s;
        ''', (id_prestito,))
        info_prestito = cur.fetchone()

        giocatore = info_prestito['nome']
        squadra_prestante = info_prestito['squadra_prestante']
        squadra_ricevente = info_prestito['squadra_ricevente']
        data_fine = formatta_data(info_prestito['data_fine'])
        richiedente_terminazione = info_prestito['richiedente_terminazione']

       
        text_to_send = textwrap.dedent(f'''
            RICHIESTA DI TERMINAZIONE PRESTITO ANTICIPATA
            La squadra {richiedente_terminazione} ha proposto di terminare in anticipo il seguente prestito:
            ⚽ Giocatore: {giocatore}
            📆 Fino a: {data_fine}
        ''')
        
        if richiedente_terminazione == squadra_prestante:
            send_message(nome_squadra=squadra_ricevente, text_to_send=text_to_send)
        else:
            send_message(nome_squadra=squadra_prestante, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)




def richiesta_terminazione_prestito_risposta(conn, id_prestito, risposta):

    if not risposta or (risposta != "Accettato" and risposta != "Rifiutato"):
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT p.giocatore, p.richiedente_terminazione
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.id = %s;
        ''', (id_prestito,))
        info_prestito = cur.fetchone()

        giocatore = info_prestito['nome']
        richiedente_terminazione = info_prestito['richiedente_terminazione']

        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''
                RICHIESTA DI TERMINAZIONE PRESTITO ANTICIPATA ACCETTATA
                La tua richiesta di terminare in anticipo il prestito del giocatore: {giocatore} è stata accettata.
            ''')
        else:
            text_to_send = textwrap.dedent(f'''
                RICHIESTA DI TERMINAZIONE PRESTITO ANTICIPATA RIFIUTATA
                La tua richiesta di terminare in anticipo il prestito del giocatore: {giocatore} è stata rifiutata.
            ''')
        
        send_message(nome_squadra=richiedente_terminazione, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(None, cur)




    
def taglio_giocatore(conn, nome_squadra, giocatore, costo_taglio):

    if not nome_squadra or not giocatore or not costo_taglio:
        print("Errore, mancano dei parametri.")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        text_to_send = textwrap.dedent(f'''
            ✂️ TAGLIO:
            La squadra {nome_squadra} ha tagliato il giocatore {giocatore}!
            💸 Costo del taglio: {costo_taglio}.
        ''')

        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome NOT IN ('Svincolato', %s);
        ''', (nome_squadra,))
        squadre_raw = cur.fetchall()
        squadre = [{"nome": s["nome"]} for s in squadre_raw]

        for s in squadre:
            print("Invio messaggio a ", s)
            send_message(nome_squadra=s['nome'], text_to_send=text_to_send)
            time.sleep(2)  # Delay per evitare spam

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)





def promozione_giocatore_primavera(conn, nome_squadra, giocatore):

    if not nome_squadra or not giocatore:
        print("Errore, mancano dei parametri.")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        text_to_send = textwrap.dedent(f'''
            🆙 PROMOZIONE PRIMAVERA:
            La squadra {nome_squadra} ha promosso in prima squadra il giocatore {giocatore}!
        ''')

        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome NOT IN ('Svincolato', %s);
        ''', (nome_squadra,))
        squadre_raw = cur.fetchall()
        squadre = [{"nome": s["nome"]} for s in squadre_raw]

        for s in squadre:
            print("Invio messaggio a ", s)
            send_message(nome_squadra=s['nome'], text_to_send=text_to_send)
            time.sleep(2)  # Delay per evitare spam

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)





def richiesta_modifica_contratto(conn, squadra_richiedente, id_giocatore, messaggio):

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT nome
                    FROM giocatore
                    WHERE id = %s;
        ''', (id_giocatore,))
        giocatore_raw = cur.fetchone()
        giocatore = giocatore_raw['nome']

        text_to_send = textwrap.dedent(f'''
            📝 Notifica ADMIN
            La squadra {squadra_richiedente} ha richiesto la modifica del contratto del giocatore {giocatore}.
            Messaggio allegato: {messaggio}
        ''')

        cur.execute('''
                    SELECT id_telegram
                    FROM admin;
        ''')
        id_admin_raw = cur.fetchone()
        id_admin = id_admin_raw['id_telegram']
        
        send_message(id=id_admin[0], text_to_send=text_to_send) # Mura
        time.sleep(1)
        send_message(id=id_admin[1], text_to_send=text_to_send) # Theo

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)




def richiesta_modifica_contratto_risposta(conn, id_richiesta, risposta):

    if risposta != "Accettato" and risposta != "Rifiutato":
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT r.squadra_richiedente, g.nome, g.tipo_contratto, r.crediti_richiesti
                    FROM richiesta_modifica_contratto AS r
                        JOIN giocatore AS g
                            ON r.giocatore = g.id
                    WHERE r.id = %s;
        ''', (id_richiesta,))
        info_richiesta = cur.fetchone()

        giocatore = info_richiesta['nome']
        tipo_contratto = info_richiesta['tipo_contratto']
        squadra_richiedente = info_richiesta['squadra_richiedente']


        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''
                📝 Modifica del contratto ACCETTATA
                L'admin di Lega ha accettato la tua richiesta di modifica del contratto del giocatore: {giocatore}.
                Nuovo contratto: {tipo_contratto}.
            ''')

        else:
            text_to_send = textwrap.dedent(f'''
                📝 Modifica del contratto RIFIUTATA
                L'admin di Lega ha rifiutato la tua richiesta di modifica del contratto del giocatore: {giocatore}.
            ''')

        
        send_message(nome_squadra=squadra_richiedente, text_to_send=text_to_send)
        
        # invia notigifica a tutte le squadre
        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome NOT IN ('Svincolato', %s);
        ''', (squadra_richiedente,))
        squadre_raw = cur.fetchall()
        squadre = [{"nome": s["nome"]} for s in squadre_raw]

        if tipo_contratto == "Svincolato":
            text_to_send = textwrap.dedent(f'''
                📝La squadra {squadra_richiedente} svincola {giocatore} a causa del suo trasferimento/svincolo e recupera {info_richiesta['crediti_richiesti']} crediti. 
            ''')
        elif tipo_contratto == "Prestito Reale":
            text_to_send = textwrap.dedent(f'''
                📝La squadra {squadra_richiedente} libera lo slot di {giocatore} a causa del suo trasferimento in prestito e recupera {info_richiesta['crediti_richiesti']} crediti. 
            ''')
        elif tipo_contratto == "Hold":
            text_to_send = textwrap.dedent(f'''
                📝La squadra {squadra_richiedente} esercita il diritto di HOLD sul giocatore {giocatore}. 
            ''')
        else:
            text_to_send = textwrap.dedent(f'''
                📝La squadra {squadra_richiedente} modifica il contratto di {giocatore} a {tipo_contratto}. 
            ''')

        for s in squadre:
            print("Invio messaggio a ", s)
            send_message(nome_squadra=s['nome'], text_to_send=text_to_send)
            time.sleep(2)  # Delay per evitare spam
            
    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        release_connection(None, cur)
        



        






    











def send_message(id=None, nome_squadra=None, text_to_send=None):

    if not text_to_send:
        print("Errore, inserire il parametro text_to_send.")
        return


    if id is not None:
        if id == 903944311:
            text_to_send = "Messaggio di routine per non far bannare il bot da Telegram."
        
        chat_id = id
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
        
            time.sleep(1)

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
