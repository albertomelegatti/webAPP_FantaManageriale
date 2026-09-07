"""
Chatbot sul regolamento.
"""

from flask import Blueprint, jsonify, render_template, request

from app.services.chatbot import get_answer

chat_bp = Blueprint('chat', __name__)


@chat_bp.route("/chat", methods=["GET", "POST"])
def chat_page():
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        user_msg = data.get("question", "").strip()

        if not user_msg:
            return jsonify({"answer": "⚠️ Inserisci una domanda valida."})

        return jsonify({"answer": get_answer(user_msg)})

    return render_template("chat.html")
