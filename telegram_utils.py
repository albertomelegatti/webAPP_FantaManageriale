import requests
import os
import time
import textwrap
from datetime import datetime
from flask import current_app
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from db import get_connection, release_connection
from user import format_giocatori, formatta_data

env_path = os.path.join(os.path.dirname(__file__), '.env')

load_dotenv(dotenv_path=env_path)
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Flag per abilitare/disabilitare notifiche (default on).
NOTIFICATIONS_ENABLED = os.getenv("NOTIFICHE_ATTIVE") == 'True'

# Cache per i telegram IDs (lazy loading)f
_TELEGRAM_IDS_CACHE = None

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

        send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
        
    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        cur.close()



def asta_iniziata(conn, id_asta):

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Recupero info per scrivere il messaggio

        cur.execute('''
                    SELECT g.nome, a.partecipanti
                    FROM asta AS a
                    JOIN giocatore AS g
                        ON a.giocatore = g.id
                    WHERE a.id = %s;
        ''', (id_asta,))
        info_asta = cur.fetchone()

        nome_giocatore = info_asta['nome']
        partecipanti = info_asta['partecipanti']

        text_to_send = textwrap.dedent(f'''
                🏷️ ASTA: {nome_giocatore}
                L'asta è iniziata!
        ''')

        for partecipante in partecipanti:
            send_message(nome_squadra=partecipante, text_to_send=text_to_send)
            time.sleep(2)  # Delay per evitare spam 

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        cur.close()
        



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
        cur.close()



def asta_conclusa(conn, id_asta):

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
        squadra_vincente = info_asta['squadra_vincente']
        ultima_offerta = info_asta['ultima_offerta']

        text_to_send = textwrap.dedent(f'''
            📢 COMUNICAZIONE UFFICIALE: 
            La squadra {squadra_vincente} acquista il giocatore {giocatore} per {ultima_offerta} crediti.
        ''')

        send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        cur.close()



def nuovo_scambio(conn, id_scambio):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT squadra_proponente, squadra_destinataria, giocatori_offerti, giocatori_richiesti, 
                           crediti_offerti, crediti_richiesti, messaggio, prestito_associato
                    FROM scambio
                    WHERE id = %s;
        ''', (id_scambio,))
        info_scambio = cur.fetchone()

        if not info_scambio:
            print(f"Nessuno scambio trovato con id: {id_scambio}")
            return

        squadra_proponente = info_scambio['squadra_proponente']
        squadra_destinataria = info_scambio['squadra_destinataria']
        giocatori_offerti_raw = format_giocatori(info_scambio['giocatori_offerti'])
        giocatori_richiesti_raw = format_giocatori(info_scambio['giocatori_richiesti'])
        giocatori_offerti_list = [f"• {g.strip()} [Definitivo]" for g in giocatori_offerti_raw.split(',') if g.strip()]
        giocatori_richiesti_list = [f"• {g.strip()} [Definitivo]" for g in giocatori_richiesti_raw.split(',') if g.strip()]
        crediti_offerti = info_scambio['crediti_offerti'] or 0
        crediti_richiesti = info_scambio['crediti_richiesti'] or 0
        messaggio = info_scambio['messaggio'] or ""
        
        prestito_associato_ids = info_scambio['prestito_associato']
        prestiti_offerti = []
        prestiti_richiesti = []

        if prestito_associato_ids:
            # Recupera prestiti collegati allo scambio
            cur.execute('''
                SELECT p.squadra_prestante, p.squadra_ricevente, p.tipo_prestito, p.crediti_riscatto,
                       g.nome as nome_giocatore
                FROM prestito p
                JOIN giocatore g ON p.giocatore = g.id
                WHERE p.id = ANY(%s)
                ORDER BY p.id;
            ''', (prestito_associato_ids,))
            prestiti = cur.fetchall()

            # Formatta prestiti offerti e richiesti
            for p in prestiti:
                tipo_map = {'secco': 'Secco', 'diritto_di_riscatto': 'DDR', 'obbligo_di_riscatto': 'ODR'}
                tipo_str = tipo_map.get(p['tipo_prestito'], p['tipo_prestito'])
                riscatto_str = f" (risc. {p['crediti_riscatto']})" if p['crediti_riscatto'] and p['crediti_riscatto'] > 0 else ""
                prestito_str = f"• {p['nome_giocatore']} [Prestito {tipo_str}{riscatto_str}]"
                
                if p['squadra_prestante'] == squadra_proponente:
                    prestiti_offerti.append(prestito_str)
                else:
                    prestiti_richiesti.append(prestito_str)

        offerta_text = "\n".join(giocatori_offerti_list)
        if prestiti_offerti:
            offerta_text += "\n" + "\n".join(prestiti_offerti)
        
        richiesta_text = "\n".join(giocatori_richiesti_list)
        if prestiti_richiesti:
            richiesta_text += "\n" + "\n".join(prestiti_richiesti)

        text_to_send = f'''🟢 NUOVA PROPOSTA DI SCAMBIO
La squadra {squadra_proponente} ti ha inviato una proposta di scambio

Offerta:
{offerta_text}
💰 Crediti offerti: {crediti_offerti}

Richiesta:
{richiesta_text}
💰 Crediti richiesti: {crediti_richiesti}

✉️ Messaggio: {messaggio}
'''

        send_message(nome_squadra=squadra_destinataria, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore in nuovo_scambio: {e}")

    finally:
        cur.close()




def scambio_risposta(conn, id_scambio, risposta):

    if not risposta or (risposta != "Accettato" and risposta != "Rifiutato"):
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT squadra_proponente, squadra_destinataria, giocatori_offerti, giocatori_richiesti, crediti_offerti, crediti_richiesti, messaggio, prestito_associato
                    FROM scambio
                    WHERE id = %s;
        ''', (id_scambio,))
        info_scambio = cur.fetchone()

        if not info_scambio:
            print(f"Nessuno scambio trovato con id: {id_scambio}")
            return

        squadra_proponente = info_scambio['squadra_proponente']
        squadra_destinataria = info_scambio['squadra_destinataria']
        giocatori_offerti_raw = format_giocatori(info_scambio['giocatori_offerti'])
        giocatori_richiesti_raw = format_giocatori(info_scambio['giocatori_richiesti'])
        giocatori_offerti_list = [f"• {g.strip()} [Definitivo]" for g in giocatori_offerti_raw.split(',') if g.strip()]
        giocatori_richiesti_list = [f"• {g.strip()} [Definitivo]" for g in giocatori_richiesti_raw.split(',') if g.strip()]
        crediti_offerti = info_scambio['crediti_offerti'] or 0
        crediti_richiesti = info_scambio['crediti_richiesti'] or 0
        messaggio = info_scambio['messaggio'] or "Nessuna Condizione."
        prestito_associato_ids = info_scambio['prestito_associato']


        # Recupera prestiti collegati allo scambio
        cur.execute('''
            SELECT p.squadra_prestante, p.squadra_ricevente, p.tipo_prestito, p.crediti_riscatto,
                   g.nome as nome_giocatore
            FROM prestito p
            JOIN giocatore g ON p.giocatore = g.id
            WHERE p.id = ANY(%s)
            ORDER BY p.id;
        ''', (prestito_associato_ids,))
        prestiti = cur.fetchall()

        # Formatta prestiti offerti e richiesti
        prestiti_offerti = []
        prestiti_richiesti = []
        for p in prestiti:
            tipo_map = {'secco': 'Secco', 'diritto_di_riscatto': 'DDR', 'obbligo_di_riscatto': 'ODR'}
            tipo_str = tipo_map.get(p['tipo_prestito'], p['tipo_prestito'])
            riscatto_str = f" (risc. {p['crediti_riscatto']})" if p['crediti_riscatto'] > 0 else ""
            prestito_str = f"• {p['nome_giocatore']} [Prestito {tipo_str}{riscatto_str}]"
            
            if p['squadra_prestante'] == squadra_proponente:
                prestiti_offerti.append(prestito_str)
            else:
                prestiti_richiesti.append(prestito_str)

        offerta_text = "\n".join(giocatori_offerti_list)
        if prestiti_offerti:
            offerta_text += "\n" + "\n".join(prestiti_offerti)
        
        richiesta_text = "\n".join(giocatori_richiesti_list)
        if prestiti_richiesti:
            richiesta_text += "\n" + "\n".join(prestiti_richiesti)

        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''\
                    SCAMBIO ACCETTATO
                    La squadra {squadra_destinataria} ha accettato la tua offerta di scambio.

                    Offerta:
                    {offerta_text}
                    💰 Crediti offerti: {crediti_offerti}

                    Richiesta:
                    {richiesta_text}
                    💰 Crediti richiesti: {crediti_richiesti}
            ''')
            send_message(nome_squadra=squadra_proponente, text_to_send=text_to_send)

            # Invia notifica a tutte le squadre
            text_to_send = textwrap.dedent(f'''\
                    📢 SCAMBIO UFFICIALE: 🔥
                    Le squadre {squadra_proponente} e {squadra_destinataria} hanno concluso un scambio:

                    ✅ {squadra_proponente} riceve:
                    ⚽
                    {richiesta_text}
                    🪙 {crediti_richiesti} crediti

                    ✅ {squadra_destinataria} riceve:
                    ⚽
                    {offerta_text}
                    🪙 {crediti_offerti} crediti

                    📝 Condizioni/Bonus: {messaggio}
            ''')
            send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)

        else:
            text_to_send = textwrap.dedent(f'''\
                    SCAMBIO RIFIUTATO
                    La squadra {squadra_destinataria} ha rifiutato la tua offerta di scambio.

                    Offerta:
                    {offerta_text}
                    💰 Crediti offerti: {crediti_offerti}

                    Richiesta:
                    {richiesta_text}
                    💰 Crediti richiesti: {crediti_richiesti}
            ''')
            send_message(nome_squadra=squadra_proponente, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        cur.close()






def nuovo_prestito(conn, id_prestito):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT g.nome, p.squadra_prestante, p.squadra_ricevente, p.data_fine,
                           p.tipo_prestito, p.costo_prestito, p.crediti_riscatto, p.note
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
        tipo_prestito = info_prestito.get('tipo_prestito') or '-'
        costo_prestito = info_prestito.get('costo_prestito') or 0
        crediti_riscatto = info_prestito.get('crediti_riscatto') or 0
        note = info_prestito.get('note') or ''

        text_to_send = textwrap.dedent(f'''
                🟢 NUOVA PROPOSTA DI PRESTITO
                La squadra {squadra_ricevente} ti ha inviato una proposta di prestito:
                ⚽ Giocatore: {giocatore}
                📆 Fino a: {data_fine}
                🧾 Tipo: {tipo_prestito}
                💸 Costo prestito: {costo_prestito}
                🪙 Riscatto: {crediti_riscatto}
                📝 Note: {note}
        ''')

        send_message(nome_squadra=squadra_prestante, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        cur.close()





def prestito_risposta(conn, id_prestito, risposta):

    if not risposta or (risposta != "Accettato" and risposta != "Rifiutato"):
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                SELECT g.nome, p.squadra_prestante, p.squadra_ricevente, p.data_fine,
                   p.tipo_prestito, p.costo_prestito, p.crediti_riscatto, p.note
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
        tipo_prestito = info_prestito.get('tipo_prestito') or '-'
        costo_prestito = info_prestito.get('costo_prestito') or 0
        crediti_riscatto = info_prestito.get('crediti_riscatto') or 0
        note = info_prestito.get('note') or 'Nessuna nota.'

        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''\
                    PRESTITO ACCETTATO
                    La squadra {squadra_prestante} ha accettato la tua richiesta di prestito:
                    ⚽ Giocatore: {giocatore}
                    📆 Fino a: {data_fine}
                    🧾 Tipo: {tipo_prestito}
                    💸 Costo prestito: {costo_prestito}
                    🪙 Riscatto: {crediti_riscatto}
                    📝 Note: {note}
            ''')
            send_message(nome_squadra=squadra_ricevente, text_to_send=text_to_send)


            text_to_send = textwrap.dedent(f'''
                    📢 PRESTITO UFFICIALE:
                                           
                    👤 {giocatore}

                    🔴 Da: {squadra_prestante}
                    🟢 A: {squadra_ricevente}
                    📅 Scadenza: {data_fine}
                    🧾 Tipo: {tipo_prestito}
                    💸 Costo prestito: {costo_prestito}
                    🪙 Riscatto: {crediti_riscatto}
                    📝 Note: {note}
            ''')
            send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
        

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
        cur.close()


def riscatto_giocatore(conn, id_prestito):
    
    #Invia notifica Telegram quando un giocatore viene riscattato
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                SELECT g.nome, p.squadra_prestante, p.squadra_ricevente, p.data_fine,
                   p.tipo_prestito, p.crediti_riscatto, p.note
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.id = %s;
        ''', (id_prestito,))
        info_prestito = cur.fetchone()

        giocatore = info_prestito['nome']
        squadra_prestante = info_prestito['squadra_prestante']
        squadra_ricevente = info_prestito['squadra_ricevente']
        crediti_riscatto = info_prestito.get('crediti_riscatto') or 0

        # Notifica al proprietario originale (squadra_prestante)
        text_to_send = textwrap.dedent(f'''\
                GIOCATORE RISCATTATO
                La squadra {squadra_ricevente} ha riscattato il giocatore {giocatore} per {crediti_riscatto} crediti.
        ''')
        send_message(nome_squadra=squadra_prestante, text_to_send=text_to_send)

        # Notifica alla squadra ricevente (che fa il riscatto)
        text_to_send = textwrap.dedent(f'''\
                GIOCATORE RISCATTATO CON SUCCESSO
                Hai riscattato {giocatore} per {crediti_riscatto} crediti.
        ''')
        send_message(nome_squadra=squadra_ricevente, text_to_send=text_to_send)
        
        # Notifica al gruppo comunicazioni
        text_to_send = textwrap.dedent(f'''\
                📢 COMUNICAZIONE UFFICIALE:
                La squadra {squadra_ricevente} ha riscattato {giocatore} dalla squadra {squadra_prestante} per {crediti_riscatto} crediti.
        ''')
        send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)

    except Exception as e:
        print(f"❌ Errore nel send_message riscatto_giocatore: {e}")

    finally:
        cur.close()




def richiesta_terminazione_prestito(conn, id_prestito):
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT g.nome, p.squadra_prestante, p.squadra_ricevente, p.data_fine, p.richiedente_terminazione
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
                🛑 RICHIESTA DI TERMINAZIONE PRESTITO ANTICIPATA            
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
        cur.close()




def richiesta_terminazione_prestito_risposta(conn, id_prestito, risposta):

    if not risposta or (risposta != "Accettato" and risposta != "Rifiutato"):
        print("Errore, il terzo parametro deve essere 'Accettato' o 'Rifiutato'")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT g.nome, p.richiedente_terminazione, p.squadra_prestante, p.squadra_ricevente, p.data_fine
                    FROM prestito p
                    JOIN giocatore g
                    ON p.giocatore = g.id
                    WHERE p.id = %s;
        ''', (id_prestito,))
        info_prestito = cur.fetchone()

        giocatore = info_prestito['nome']
        richiedente_terminazione = info_prestito['richiedente_terminazione']
        squadra_prestante = info_prestito['squadra_prestante']
        squadra_ricevente = info_prestito['squadra_ricevente']
        
        if risposta == "Accettato":
            text_to_send = textwrap.dedent(f'''
                    RICHIESTA DI TERMINAZIONE PRESTITO ANTICIPATA ACCETTATA
                    La tua richiesta di terminare in anticipo il prestito del giocatore: {giocatore} è stata accettata.
            ''')
            send_message(nome_squadra=richiedente_terminazione, text_to_send=text_to_send)
            
            text_to_send = textwrap.dedent(f'''
                    📢 COMUNICAZIONE UFFICIALE: 
                    Le squadre {squadra_prestante} e {squadra_ricevente} si sono accordate per terminare anticipatamente il prestito del giocatore: {giocatore}.
            ''')
            send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)


        else:
            text_to_send = textwrap.dedent(f'''
                    RICHIESTA DI TERMINAZIONE PRESTITO ANTICIPATA RIFIUTATA
                    La tua richiesta di terminare in anticipo il prestito del giocatore: {giocatore} è stata rifiutata.
            ''')
        send_message(nome_squadra=richiedente_terminazione, text_to_send=text_to_send)

    except Exception as e:
        print(f"Errore: {e}")

    finally:
        cur.close()




    
def taglio_giocatore(conn, nome_squadra, giocatore, costo_taglio):

    if not nome_squadra or not giocatore or not costo_taglio:
        print("Errore, mancano dei parametri.")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        text_to_send = textwrap.dedent(f'''
                ✂️ COMUNICAZIONE UFFICIALE: 
                La squadra {nome_squadra} svincola il giocatore {giocatore} pagando {costo_taglio} crediti.
        ''')

        send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
        
    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        cur.close()





def promozione_giocatore_primavera(conn, nome_squadra, giocatore):

    if not nome_squadra or not giocatore:
        print("Errore, mancano dei parametri.")
        return
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        text_to_send = textwrap.dedent(f'''
                🆙 COMUNICAZIONE UFFICIALE: 
                La squadra {nome_squadra} promuove in prima squadra il giocatore {giocatore}
        ''')

        send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
        
    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        cur.close()





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
        cur.close()




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
        
        # invia notifica a tutte le squadre
        if risposta == "Accettato":

            if tipo_contratto == "Svincolato":
                text_to_send = textwrap.dedent(f'''
                        📢 COMUNICAZIONE UFFICIALE: 
                        📝La squadra {squadra_richiedente} svincola {giocatore} a causa del suo trasferimento/svincolo e recupera {info_richiesta['crediti_richiesti']} crediti. 
                ''')

            elif tipo_contratto == "Prestito Reale":
                text_to_send = textwrap.dedent(f'''
                        📢 COMUNICAZIONE UFFICIALE:
                        📝La squadra {squadra_richiedente} libera lo slot di {giocatore} a causa del suo trasferimento in prestito e recupera {info_richiesta['crediti_richiesti']} crediti. 
                ''')

            elif tipo_contratto == "Hold":
                text_to_send = textwrap.dedent(f'''
                        📢 COMUNICAZIONE UFFICIALE: 
                        📝La squadra {squadra_richiedente} esercita il diritto di HOLD sul giocatore {giocatore}. 
                ''')

            else:
                text_to_send = textwrap.dedent(f'''
                        📢 COMUNICAZIONE UFFICIALE: 
                        📝La squadra {squadra_richiedente} modifica il contratto di {giocatore} a {tipo_contratto}. 
                ''')

            send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
            
    except Exception as e:
        print(f"Errore: {e}")
    
    finally:
        cur.close()



def salva_movimento(text_to_send):
    # Salva il messaggio nella tabella movimenti_squadra

    conn = None
    cur = None
    
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        text_to_send = text_to_send.replace('\n', ' ').strip()

        cur.execute('''
                    INSERT INTO movimenti_squadra (evento, data, stagione)
                    VALUES (%s, NOW(), %s)
        ''', (text_to_send, get_stagione()))
        
        conn.commit()
        print(f"✅ Movimento salvato nel database")
        
    except Exception as e:
        print(f"❌ Errore nel salvataggio del movimento: {e}")
        if conn:
            conn.rollback()
    
    finally:
        release_connection(conn, cur)





def send_message(id=None, nome_squadra=None, text_to_send=None):
    
    if not text_to_send:
        print("Errore, inserire il parametro text_to_send.")
        return

    if not NOTIFICATIONS_ENABLED:
        print("ℹ️ Notifiche disattivate (NOTIFICHE_ATTIVE=0)")
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

    # Salva il movimento se destinatario è il gruppo_comunicazioni
    if nome_squadra == 'gruppo_comunicazioni':
        salva_movimento(text_to_send)

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



def get_stagione():
    
    # Calcola la stagione in base alla data attuale.
    # La stagione va dal 2 luglio di un anno al 2 luglio dell'anno successivo.
    # Esempi: 25-26 (dal 2 luglio 2025 al 2 luglio 2026)
    
    today = datetime.now()
    year = today.year
    month = today.month
    day = today.day
    
    # Se siamo prima del 2 luglio, la stagione è dell'anno precedente
    if month < 7 or (month == 7 and day < 2):
        stagione_start = year - 1
    else:
        stagione_start = year
    
    stagione_end = stagione_start + 1
    
    # Restituisci nel formato "25-26"
    return f"{stagione_start % 100:02d}-{stagione_end % 100:02d}"
        




def get_all_telegram_ids():
    # Lazy loading: carica i dati solo al primo accesso
    global _TELEGRAM_IDS_CACHE
    
    if _TELEGRAM_IDS_CACHE is not None:
        return _TELEGRAM_IDS_CACHE

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

        cur.execute('''
                    SELECT id_gruppo_comunicazioni
                    FROM admin;
        ''')
        id_gruppo_comunicazioni_raw = cur.fetchone()
        id_gruppo_comunicazioni = id_gruppo_comunicazioni_raw['id_gruppo_comunicazioni']
        SQUADRE_IDS['gruppo_comunicazioni'] = [id_gruppo_comunicazioni]

        _TELEGRAM_IDS_CACHE = SQUADRE_IDS
        print("✅ Inizializzato dizionario ID telegram")
        #print(SQUADRE_IDS)

        return SQUADRE_IDS


    except Exception as e:
        print(f"❌ Errore critico nel fetching della mappa ID: {e}")
        return {}

    finally:
        release_connection(conn, cur)


