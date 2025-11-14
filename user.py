import psycopg2
from flask import Blueprint, render_template
from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
from datetime import datetime

user_bp = Blueprint('user', __name__, url_prefix='/user')

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadraLogin/<nome_squadra>")
def squadraLogin(nome_squadra):
    return render_template("squadraLogin.html", nome_squadra=nome_squadra)



def format_partecipanti(partecipanti):
    if not partecipanti:
        return ""
    elif len(partecipanti) == 1:
        return partecipanti[0]
    else:
        return ",\n".join(partecipanti)
    


def format_giocatori(giocatori):
    if not giocatori:
        return ""
    
    if isinstance(giocatori, int):
        giocatori = [giocatori]
    
    conn = None
    cur = None
    nomi_ordinati = []

    try:
        conn = get_connection()
        cur = conn.cursor() 

        cur.execute('''
            SELECT id, nome
            FROM giocatore
            WHERE id IN %s;
        ''', (tuple(giocatori),)) # Passa la lista come una tupla
        
        # Mappa i risultati {id: nome}
        # row[0] è l'ID, row[1] è il nome
        risultati_map = {row[0]: row[1] for row in cur.fetchall()} 
        
        # 3. Formattazione e Mantenimento dell'Ordine (Cruciale)
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
        release_connection(conn, cur)
    
    if not nomi_ordinati:
        return ""
    elif len(nomi_ordinati) == 1:
        return nomi_ordinati[0]
    else:
        # Ritorna la lista formattata (es: "Nome1, Nome2, Nome3")
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


