"""Draft U21 live: il tabellone e la scelta per la squadra on the clock.

La pagina e' riservata a chi ha fatto il login: ci si arriva dalla dashboard
della squadra, non dalla home pubblica. Scegliere vale solo quando la pick in
corso e' della propria squadra; l'admin sceglie per gli assenti dalla propria
pagina (vedi admin.py).
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from app import telegram_utils
from app.core.db import connessione
from app.core.formato import url_campioncino
from app.core.logging import get_logger
from app.repositories import draft as draft_repo
from app.repositories import draft_sessione as sessione_repo
from app.services import draft_live

logger = get_logger(__name__)

draft_bp = Blueprint("draft", __name__, url_prefix="/draft/live")


def annuncia(cur, anno: int, esito: dict, *, evento: str, da_admin: bool = False) -> None:
    """Messaggi Telegram per l'esito di un'operazione del draft.

    Va chiamata DOPO il commit: se l'operazione e' stata annullata non si
    annuncia niente. `evento` e' "apertura", "scelta" o "salto". Il rigo "Ora
    tocca a ..." sta solo sull'ultimo messaggio, quando ce ne sono piu' d'uno
    (una scelta seguita da pick saltate per slot pieni).
    """
    prossima = draft_repo.pick_in_corso(cur, anno)
    messaggi = []

    if evento == "apertura":
        messaggi.append(lambda p: telegram_utils.draft_aperto(anno, p))
    elif evento == "scelta":
        pick, giocatore = esito["pick"], esito["giocatore"]
        messaggi.append(lambda p: telegram_utils.draft_scelta(
            anno, pick["detentore_att"], giocatore["nome"], pick["numero"], p, da_admin))
    elif evento == "salto":
        pick = esito["pick"]
        messaggi.append(lambda p: telegram_utils.draft_pick_saltata(
            anno, pick["detentore_att"], pick["numero"], "saltata dall'admin", p))

    for saltata in esito.get("saltate", []):
        messaggi.append(lambda p, s=saltata: telegram_utils.draft_pick_saltata(
            anno, s["detentore_att"], s["numero"], "slot Primavera pieni", p))

    # Con "apertura" il primo messaggio annuncia gia' di chi e' il turno iniziale:
    # le pick saltate subito dopo spostano il turno, quindi l'ultimo lo ricorda.
    for i, invia in enumerate(messaggi):
        invia(prossima if i == len(messaggi) - 1 else None)

    if esito.get("concluso"):
        telegram_utils.draft_concluso(anno, draft_live.riepilogo(cur, anno))


@draft_bp.before_request
def richiedi_login():
    if not session.get("logged_in"):
        flash("Accedi per seguire il draft.", "warning")
        return redirect(url_for("auth.login"))


@draft_bp.route("/")
def live():
    squadra = session.get("nome_squadra")

    with connessione() as (conn, cur):
        sessione = sessione_repo.ultima(cur)
        if sessione is None:
            return render_template("draft_live.html", vista=None)

        vista = draft_live.vista(cur, sessione["anno"])
        tocca_a_me = bool(squadra and vista["in_corso"]
                          and vista["in_corso"]["detentore_att"] == squadra)
        pool = [{**g, "campioncino": url_campioncino(g["id_fantacalcio"])}
                for g in draft_live.pool(cur)] if tocca_a_me else []

    return render_template("draft_live.html", vista=vista, squadra=squadra,
                           tocca_a_me=tocca_a_me, pool=pool)


@draft_bp.route("/scegli", methods=["POST"])
def scegli():
    squadra = session.get("nome_squadra")
    if not squadra:
        # Un admin e' loggato ma non ha una squadra: sceglie dalla sua pagina.
        flash("Solo una squadra puo' scegliere da qui: l'admin usa la pagina Draft U21.", "warning")
        return redirect(url_for("draft.live"))

    try:
        anno = int(request.form["anno"])
        id_pick = int(request.form["id_pick"])
        id_giocatore = int(request.form["id_giocatore"])
    except (KeyError, ValueError):
        flash("❌ Richiesta non valida.", "danger")
        return redirect(url_for("draft.live"))

    with connessione() as (conn, cur):
        try:
            esito = draft_live.scegli(cur, anno, id_pick, id_giocatore,
                                      squadra=squadra, e_admin=False, da=squadra)
            conn.commit()
        except draft_live.SceltaNonValida as e:
            conn.rollback()
            flash(f"❌ {e}", "danger")
            return redirect(url_for("draft.live"))
        annuncia(cur, anno, esito, evento="scelta")

    logger.info("Draft %s: %s sceglie %s (pick %s)", anno, squadra,
                esito["giocatore"]["nome"], esito["pick"]["numero"])
    flash(f"✅ Hai scelto {esito['giocatore']['nome']}.", "success")
    return redirect(url_for("draft.live"))
