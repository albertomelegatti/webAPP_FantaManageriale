from flask import Blueprint, render_template, session, redirect, url_for
from app.core.db import connessione

from app.core.logging import get_logger
from app.repositories import aste as aste_repo
from app.repositories import configurazione as configurazione_repo
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
    return redirect(url_for("pubblico.home"))

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadra_login/<nome_squadra>")
def squadra_login(nome_squadra):

    with connessione() as (conn, cur):
        cur.execute("SELECT username FROM squadra WHERE nome = %s;", (nome_squadra,))
        username = cur.fetchone()["username"]

        slot_giocatori = giocatori_repo.slot_occupati_da_giocatori(cur, nome_squadra)
        slot_aste = aste_repo.slot_impegnati(cur, nome_squadra)
        slot_occupati = slot_giocatori + slot_aste
        prestiti_in_num = giocatori_repo.slot_prestiti_in(cur, nome_squadra)

        crediti = squadre_repo.crediti(cur, nome_squadra)

    return render_template("squadra_login.html", nome_squadra=nome_squadra, username=username, slot_giocatori=slot_giocatori, slot_aste=slot_aste, slot_occupati=slot_occupati, prestiti_in_num=prestiti_in_num, crediti=crediti)


def _info_chiusura(chiusura, aperto, testo):
    """Testo per il tooltip di una voce di menu disabilitata, es. 'Chiuso dal 02/09/2026'."""
    if aperto or not chiusura:
        return None
    return f"{testo} dal {chiusura.strftime('%d/%m/%Y')}"


@user_bp.route("/mercato_menu/<nome_squadra>")
def user_mercato_menu(nome_squadra):
    with connessione() as (conn, cur):
        stato_gate = configurazione_repo.stato_gate(cur)
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
    with connessione() as (conn, cur):
        stato_gate = configurazione_repo.stato_gate(cur)
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
