from flask import Blueprint, render_template, session, redirect, url_for
from app.core.db import connessione

from app.core.logging import get_logger
from app.repositories import albo_oro as albo_oro_repo
from app.repositories import aste as aste_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import draft_sessione as draft_sessione_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import squadre as squadre_repo

logger = get_logger(__name__)


user_bp = Blueprint('user', __name__, url_prefix='/user')


def redirect_gate_chiuso():
    """Redirect da usare quando una sezione (mercato o aste) è chiusa: torna alla
    home della squadra loggata, se nota, altrimenti alla home generale."""
    nome_squadra = session.get("nome_squadra")
    if nome_squadra:
        return redirect(url_for("user.squadra_login", nome_squadra=nome_squadra))
    return redirect(url_for("public.home"))

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadra_login/<nome_squadra>")
def squadra_login(nome_squadra):

    with connessione() as (conn, cur):
        username = squadre_repo.username(cur, nome_squadra)

        slot_giocatori = giocatori_repo.slot_occupati_da_giocatori(cur, nome_squadra)
        slot_aste = aste_repo.slot_impegnati(cur, nome_squadra)
        slot_occupati = slot_giocatori + slot_aste
        prestiti_in_num = giocatori_repo.slot_prestiti_in(cur, nome_squadra)

        crediti = squadre_repo.crediti(cur, nome_squadra)
        palmares = albo_oro_repo.palmares(cur, nome_squadra)
        draft_aperto = draft_sessione_repo.aperto(cur) is not None
        stato_gate = configurazione_repo.stato_gate(cur)

    return render_template(
        "squadra_login.html", nome_squadra=nome_squadra, username=username,
        slot_giocatori=slot_giocatori, slot_aste=slot_aste, slot_occupati=slot_occupati,
        prestiti_in_num=prestiti_in_num, crediti=crediti, palmares=palmares,
        draft_aperto=draft_aperto,
        # Le voci di mercato e aste stanno direttamente in dashboard e, a gate
        # chiuso, non si mostrano.
        mercato_aperto=stato_gate["mercato_aperto"],
        aste_aperte=stato_gate["aste_aperte"],
    )


def format_partecipanti(partecipanti):
    if not partecipanti:
        return ""
    elif len(partecipanti) == 1:
        return partecipanti[0]
    else:
        return ",\n".join(partecipanti)
