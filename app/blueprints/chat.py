"""
Chatbot sul regolamento.

Corpo della funzione spostato da main.py senza modifiche di logica.

Nota per le fasi successive: `chat_history` è una lista globale condivisa fra
tutti gli utenti e non thread-safe (il Procfile usa 4 thread per worker).
Viene scritta e mai riletta, quindi oggi è solo ritenzione di memoria. La sua
rimozione è nella Fase 8 del piano, perché cambia il comportamento.
"""

from flask import Blueprint, jsonify, render_template, request

from app.services.chatbot import get_answer

chat_bp = Blueprint('chat', __name__)

chat_history = []


@chat_bp.route("/chat", methods=["GET", "POST"])
def chat_page():
    global chat_history

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        user_msg = data.get("question", "").strip()

        if not user_msg:
            return jsonify({"answer": "⚠️ Inserisci una domanda valida."})

        bot_msg = get_answer(user_msg)

        chat_history.append((user_msg, bot_msg))
        chat_history = chat_history[-2:]

        return jsonify({"answer": bot_msg})

    return render_template("chat.html")
