import telegram_utils
import textwrap
from flask import Blueprint, request, jsonify, current_app
from psycopg2.extras import RealDictCursor
from db import get_connection, release_connection

webhook_bp = Blueprint('webhook_bp', __name__)

@webhook_bp.route("/webhook/update_stato_asta", methods=["POST"])
def webhook_update_stato_asta():
    
    #Gestisce il webhook da Supabase per l'aggiornamento dello stato delle aste.
    #Invia una notifica Telegram quando un'asta passa da 'mostra_interesse' a 'in_corso'.
    
    try:
        data = request.json
        conn = None
        conn = get_connection()

        # Log per debug
        print("Webhook ricevuto:", data)

        if data and data.get("type") == "UPDATE" and "record" in data and "old_record" in data:
            old_status = data["old_record"].get("stato")
            new_status = data["record"].get("stato")
            id_asta = data["record"].get("id")

            try:

                if old_status == "mostra_interesse" and new_status == "in_corso":
                    telegram_utils.asta_iniziata(conn, id_asta)

                if old_status == "in_corso" and new_status == "conclusa":
                    telegram_utils.asta_conclusa(conn, id_asta)


            except Exception as e:
                print(f"Errore durante l'elaborazione del webhook: {e}")
                    

    except Exception as e:
        print(f"Errore nella ricezione del webhook: {e}")

    finally:
        release_connection(conn, None)


    return jsonify({"status": "success"}), 200
