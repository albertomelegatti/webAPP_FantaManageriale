from flask import Blueprint, request, jsonify, current_app
from psycopg2.extras import RealDictCursor
import telegram_utils
from db import get_connection, release_connection

webhook_bp = Blueprint('webhook_bp', __name__)

@webhook_bp.route("/webhook/update_stato_asta", methods=["POST"])
def webhook_update_stato_asta():
    
    #Gestisce il webhook da Supabase per l'aggiornamento dello stato delle aste.
    #Invia una notifica Telegram quando un'asta passa da 'mostra_interesse' a 'in_corso'.
    
    try:
        data = request.json
        
        # Log per debug
        print("Webhook ricevuto:", data)

        if data and data.get("type") == "UPDATE" and "record" in data and "old_record" in data:
            old_status = data["old_record"].get("stato")
            new_status = data["record"].get("stato")
            id_asta = data["record"].get("id")
            id_giocatore = data["record"].get("giocatore")

            if old_status == "mostra_interesse" and new_status == "in_corso":
                conn = None
                cur = None
                try:
                    conn = get_connection()
                    cur = conn.cursor(cursor_factory=RealDictCursor)

                    # Recupera il nome del giocatore
                    cur.execute("SELECT nome FROM giocatore WHERE id = %s", (id_giocatore,))
                    giocatore = cur.fetchone()

                    if giocatore:
                        nome_giocatore = giocatore["nome"]
                        
                        # Prepara e invia la notifica
                        text_to_send = f"📣 L'asta per **{nome_giocatore}** è iniziata! 🚀\n\n"(
                            f"📣 L'asta per **{nome_giocatore}** è iniziata! 🚀\n\n"
                            f"Fai la tua offerta ora!"
                        )
                        
                        # Invia notifica a tutti gli utenti registrati su Telegram
                        telegram_ids = current_app.config.get('SQUADRE_TELEGRAM_IDS', {}).values()
                        for chat_id in telegram_ids:
                            telegram_utils.send_message(chat_id, message, parse_mode="Markdown")

                        print(f"Notifica inviata per l'asta {id_asta} del giocatore {nome_giocatore}")

                except Exception as e:
                    print(f"Errore durante l'elaborazione del webhook: {e}")
                finally:
                    release_connection(conn, cur)

    except Exception as e:
        print(f"Errore nella ricezione del webhook: {e}")

    return jsonify({"status": "success"}), 200
