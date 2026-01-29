from flask import Blueprint, render_template
from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
from datetime import datetime
from queries import get_slot_occupati, get_slot_aste, get_slot_giocatori, get_slot_prestiti_in


user_bp = Blueprint('user', __name__, url_prefix='/user')

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadra_login/<nome_squadra>")
def squadra_login(nome_squadra):

    conn = get_connection()
    
    slot_giocatori = get_slot_giocatori(conn, nome_squadra)
    slot_aste = get_slot_aste(conn, nome_squadra)
    slot_occupati = get_slot_occupati(conn, nome_squadra)
    prestiti_in_num = get_slot_prestiti_in(conn, nome_squadra)

    release_connection(conn, None)

    return render_template("squadra_login.html", nome_squadra=nome_squadra, slot_giocatori=slot_giocatori, slot_aste=slot_aste, slot_occupati=slot_occupati, prestiti_in_num=prestiti_in_num)



def format_partecipanti(partecipanti):
    if not partecipanti:
        return ""
    elif len(partecipanti) == 1:
        return partecipanti[0]
    else:
        return ",\n".join(partecipanti)
    


def format_giocatori(conn, giocatori):
    if not giocatori:
        return ""
    
    if isinstance(giocatori, int):
        giocatori = [giocatori]
    
    cur = None
    nomi_ordinati = []

    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
            SELECT id, nome
            FROM giocatore
            WHERE id = ANY(%s);
        ''', (giocatori,))
        
        # Mappa i risultati {id: nome}
        risultati_map = {row['id']: row['nome'] for row in cur.fetchall()} 
        
        # Formattazione e Mantenimento dell'Ordine (Cruciale)
        for giocatore_id in giocatori:
            nome = risultati_map.get(giocatore_id)
            if nome:
                nomi_ordinati.append(nome)
            else:
                nomi_ordinati.append(f"ID {giocatore_id} (non trovato)")

    except Exception as e:
        print(f"❌ Errore durante il recupero dei nomi giocatori: {e}")
        return "Errore nel recupero dei giocatori"

    finally:
        cur.close()
    
    if not nomi_ordinati:
        return ""
    elif len(nomi_ordinati) == 1:
        return nomi_ordinati[0]
    else:
        # Ritorna i nomi formattati (es: "Nome1, Nome2, Nome3")
        return ", ".join(nomi_ordinati)



def formatta_data(data_input):

    #Converte una data (stringa o datetime) in formato 'dd/mm/YYYY HH:MM'.
    #Rimuove automaticamente millisecondi e timezone.
    
    if data_input is None:
        return None

    # Se è una stringa ISO, puliscila
    if isinstance(data_input, str):
        # Rimuove millisecondi e timezone se presenti
        data_input = data_input.split("+")[0].split("Z")[0].split(".")[0]
        try:
            data_input = datetime.fromisoformat(data_input)
        except ValueError:
            return data_input  # se non è una data ISO valida, restituisci com'è

    # Se è un oggetto datetime, formatta
    if isinstance(data_input, datetime):
        return data_input.strftime("%d/%m/%Y %H:%M")

    return str(data_input)


