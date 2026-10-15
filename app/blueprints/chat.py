"""
Chatbot sul regolamento e sui dati della lega.
"""

from flask import Blueprint, jsonify, render_template, request

from app.services.chatbot import get_answer

chat_bp = Blueprint('chat', __name__)


@chat_bp.route("/chat", methods=["GET", "POST"])
def chat_page():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}

        # La conversazione intera la tiene il browser e la rimanda a ogni
        # domanda; "question" resta per chi invia ancora una domanda singola.
        messaggi = data.get("messages")
        if not messaggi:
            domanda = str(data.get("question", "")).strip()
            messaggi = [{"role": "user", "content": domanda}] if domanda else []

        if not messaggi:
            return jsonify({"answer": "⚠️ Inserisci una domanda valida."})

        return jsonify({"answer": get_answer(messaggi)})

    return render_template("chat.html")
