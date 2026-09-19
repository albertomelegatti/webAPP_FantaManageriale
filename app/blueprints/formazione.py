"""Formazione (campetto): editor privato per la squadra proprietaria."""

from flask import Blueprint, render_template, redirect, url_for, flash, request, session

from app.core.db import connessione
from app.core.logging import get_logger
from app.domini import moduli
from app.services import formazione as servizio_formazione

logger = get_logger(__name__)

formazione_bp = Blueprint('formazione', __name__, url_prefix='/formazione')


@formazione_bp.route("/user_formazione/<nome_squadra>", methods=["GET", "POST"])
def user_formazione(nome_squadra):
    if session.get("nome_squadra") != nome_squadra:
        flash("❌ Puoi modificare solo la formazione della tua squadra.", "danger")
        return redirect(url_for("auth.login"))

    with connessione() as (conn, cur):
        if request.method == "POST":
            modulo = request.form.get("modulo", "")

            selezioni = {}
            for indice in range(len(moduli.MODULI.get(modulo, []))):
                selezioni[indice] = {
                    posto: request.form.get(f"slot_{indice}_{posto}", "")
                    for posto in moduli.POSTI
                }

            errori = servizio_formazione.salva(cur, nome_squadra, modulo, selezioni)

            if errori:
                for errore in errori:
                    flash(f"❌ {errore}", "danger")
                dati = servizio_formazione.dati_editor(cur, nome_squadra, modulo)
                return render_template("user_formazione.html", nome_squadra=nome_squadra, **dati)

            conn.commit()
            flash("✅ Formazione salvata.", "success")
            return redirect(url_for("formazione.user_formazione", nome_squadra=nome_squadra))

        modulo_richiesto = request.args.get("modulo")
        dati = servizio_formazione.dati_editor(cur, nome_squadra, modulo_richiesto)

    return render_template("user_formazione.html", nome_squadra=nome_squadra, **dati)
