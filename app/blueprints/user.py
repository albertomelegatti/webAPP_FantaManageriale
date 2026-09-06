from flask import Blueprint, render_template, session, redirect, url_for
from app.core.db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
from datetime import datetime
from app.queries import get_slot_aste, get_slot_giocatori, get_slot_prestiti_in, get_crediti_squadra, get_stato_gate


user_bp = Blueprint('user', __name__, url_prefix='/user')


def redirect_gate_chiuso():
    """Redirect da usare quando una sezione (mercato o aste) è chiusa: torna alla
    home della squadra loggata, se nota, altrimenti alla home generale."""
    nome_squadra = session.get("nome_squadra")
    if nome_squadra:
        return redirect(url_for("user.squadra_login", nome_squadra=nome_squadra))
    return redirect(url_for("home"))

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadra_login/<nome_squadra>")
def squadra_login(nome_squadra):

    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT username FROM squadra WHERE nome = %s;", (nome_squadra,))
    username = cur.fetchone()["username"]

    slot_giocatori = get_slot_giocatori(conn, nome_squadra)
    slot_aste = get_slot_aste(conn, nome_squadra)
    slot_occupati = slot_giocatori + slot_aste
    prestiti_in_num = get_slot_prestiti_in(conn, nome_squadra)

    crediti = get_crediti_squadra(conn, nome_squadra)

    release_connection(conn, cur)

    return render_template("squadra_login.html", nome_squadra=nome_squadra, username=username, slot_giocatori=slot_giocatori, slot_aste=slot_aste, slot_occupati=slot_occupati, prestiti_in_num=prestiti_in_num, crediti=crediti)


def _info_chiusura(chiusura, aperto, testo):
    """Testo per il tooltip di una voce di menu disabilitata, es. 'Chiuso dal 02/09/2026'."""
    if aperto or not chiusura:
        return None
    return f"{testo} dal {chiusura.strftime('%d/%m/%Y')}"


@user_bp.route("/mercato_menu/<nome_squadra>")
def user_mercato_menu(nome_squadra):
    conn = get_connection()
    stato_gate = get_stato_gate(conn)
    release_connection(conn)
    return render_template(
        "user_mercato_menu.html",
        nome_squadra=nome_squadra,
        mercato_aperto=stato_gate["mercato_aperto"],
        aste_aperte=stato_gate["aste_aperte"],
        mercato_info=_info_chiusura(stato_gate["mercato_chiusura"], stato_gate["mercato_aperto"], "Chiuso"),
        aste_info=_info_chiusura(stato_gate["aste_chiusura"], stato_gate["aste_aperte"], "Chiuse"),
    )


@user_bp.route("/prestiti_menu/<nome_squadra>")
def user_prestiti_menu(nome_squadra):
    conn = get_connection()
    stato_gate = get_stato_gate(conn)
    release_connection(conn)
    return render_template(
        "user_prestiti_menu.html",
        nome_squadra=nome_squadra,
        mercato_aperto=stato_gate["mercato_aperto"],
        mercato_info=_info_chiusura(stato_gate["mercato_chiusura"], stato_gate["mercato_aperto"], "Chiuso"),
    )


@user_bp.route("/rosa_menu/<nome_squadra>")
def user_rosa_menu(nome_squadra):
    return render_template("user_rosa_menu.html", nome_squadra=nome_squadra)



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
        release_connection(conn, cur)
    
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


