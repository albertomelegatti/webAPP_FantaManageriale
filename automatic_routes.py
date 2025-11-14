from flask import Blueprint, requests
from telegram_utils import asta_iniziata
from db import get_connection, release_connection

automatic_routes_bp = Blueprint("automatic_routes", __name__)

@automatic_routes_bp.post("/notifica_asta_iniziata")
def notifica_asta_iniziata():
    data = requests.json
    id_asta = data["id_asta"]

    conn = get_connection()
    asta_iniziata(conn, id_asta)
    release_connection(conn, None)

    return {"status": "ok"}
