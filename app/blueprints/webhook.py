from flask import Blueprint, jsonify, request

from app import telegram_utils
from app.core.db import connessione

from app.core.logging import get_logger

logger = get_logger(__name__)

webhook_bp = Blueprint('webhook_bp', __name__)


@webhook_bp.route("/webhook/update_stato_asta", methods=["POST"])
def webhook_update_stato_asta():

    #Gestisce il webhook da Supabase per l'aggiornamento dello stato delle aste.
    #Invia una notifica Telegram quando un'asta passa da 'mostra_interesse' a 'in_corso'.

    try:
        data = request.json

        # Log per debug
        logger.info("Webhook ricevuto: %s", data)

        if data and data.get("type") == "UPDATE" and "record" in data and "old_record" in data:
            old_status = data["old_record"].get("stato")
            new_status = data["record"].get("stato")
            id_asta = data["record"].get("id")

            # Controlla che ci sia effettivamente un cambiamento dello stato
            if old_status != new_status:
                try:
                    # La connessione serve solo per comporre le notifiche, quindi
                    # viene presa qui e non all'inizio della richiesta: un webhook
                    # senza cambio di stato non tocca piu' il pool.
                    with connessione() as (conn, _):
                        if old_status == "mostra_interesse" and new_status == "in_corso":
                            telegram_utils.asta_iniziata(conn, id_asta)

                        if (old_status == "in_corso" and new_status == "conclusa") or (old_status == "mostra_interesse" and new_status == "conclusa"):
                            telegram_utils.asta_conclusa(conn, id_asta)

                except Exception as e:
                    logger.exception("Errore durante l'elaborazione del webhook")
            else:
                logger.info(f"Webhook ignorato: nessun cambio di stato per asta {id_asta}")

    except Exception as e:
        logger.exception("Errore nella ricezione del webhook")

    logger.info("Invio risposta al database...")
    return jsonify({"status": "success"}), 200
