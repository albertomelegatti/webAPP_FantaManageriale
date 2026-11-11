"""Draft U21 live: apertura, scelta di un giocatore, pick saltate.

Le funzioni lavorano su un cursore e non fanno commit: il chiamante (la route)
committa, o annulla se sale un'eccezione. Telegram parte dalla route dopo il
commit, come per le altre operazioni, cosi' una scelta annullata non annuncia
niente.

Regole (regolamento 3.1):
- si sceglie solo la pick "on the clock", cioe' il numero piu' basso non ancora
  usato ne' saltato; la scelta spetta a chi detiene la pick (`detentore_att`),
  o a un admin per conto di un assente;
- il giocatore va in Primavera a costo 0, senza toccare i crediti;
- una squadra con tutti gli slot Primavera occupati perde la pick: quando
  arriva il suo turno la pick viene saltata da sola;
- quando non resta nessuna pick da usare il draft si chiude da solo.
"""

from app.domini.draft_ordine import (
    OrdineNonValido, ordine_da_classifica, stagione_della_classifica)
from app.domini.ruoli import pulisci_ruolo
from app.repositories import albo_oro as albo_oro_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import draft as draft_repo
from app.repositories import draft_sessione as sessione_repo
from app.repositories import giocatori as giocatori_repo

SLOT_PRIMAVERA = 5

# Chi risulta in `draft.scelta_da` quando e' il sistema a saltare la pick.
SISTEMA = "sistema"


class SceltaNonValida(ValueError):
    """La richiesta non si puo' eseguire; il messaggio e' per l'utente."""


def _salta_pick_senza_slot(cur, anno: int) -> list[dict]:
    """Salta le pick in corso la cui squadra non ha slot Primavera liberi.

    Si ripete: saltata una pick, la successiva puo' essere della stessa
    squadra (o di un'altra con gli slot pieni).
    """
    saltate = []
    while True:
        pick = draft_repo.pick_in_corso(cur, anno)
        if pick is None:
            return saltate
        if giocatori_repo.conta_primavera(cur, pick["detentore_att"]) < SLOT_PRIMAVERA:
            return saltate
        draft_repo.salta_pick(cur, pick["id"], SISTEMA)
        saltate.append(pick)


def _chiudi_se_finito(cur, anno: int) -> bool:
    if draft_repo.pick_in_corso(cur, anno) is None:
        return sessione_repo.chiudi(cur, anno)
    return False


def apri(cur, anno: int) -> dict:
    """preparato -> aperto. Le prime pick di squadre senza slot saltano subito.

    Ritorna {saltate, concluso}.
    """
    if draft_repo.pick_in_corso(cur, anno) is None:
        raise SceltaNonValida(
            f"Il draft {anno} non ha un ordine generato: generalo prima di aprirlo.")
    if not sessione_repo.apri(cur, anno):
        raise SceltaNonValida(f"Il draft {anno} non e' nello stato 'preparato'.")
    saltate = _salta_pick_senza_slot(cur, anno)
    return {"saltate": saltate, "concluso": _chiudi_se_finito(cur, anno)}


def _pick_valida(cur, anno: int, id_pick: int) -> dict:
    """La pick indicata, bloccata, solo se e' proprio quella in corso.

    Il form manda l'id della pick che l'utente vedeva "on the clock": se nel
    frattempo il turno e' passato (un altro ha scelto, l'admin ha saltato) la
    richiesta e' vecchia e si rifiuta, invece di consumare la pick sbagliata.
    """
    sessione = sessione_repo.leggi(cur, anno)
    if not sessione or sessione["stato"] != "aperto":
        raise SceltaNonValida(f"Il draft {anno} non e' aperto.")

    pick = draft_repo.blocca_pick(cur, id_pick)
    if pick is None or pick["anno"] != anno:
        raise SceltaNonValida("Pick inesistente.")
    in_corso = draft_repo.pick_in_corso(cur, anno)
    if in_corso is None or in_corso["id"] != pick["id"]:
        raise SceltaNonValida("Il turno e' cambiato: ricarica la pagina.")
    return pick


def scegli(cur, anno: int, id_pick: int, id_giocatore: int, *,
           squadra: str | None, e_admin: bool, da: str) -> dict:
    """Assegna `id_giocatore` alla squadra che detiene la pick in corso.

    `squadra` e' chi ha fatto la richiesta (dal login); `da` e' cio' che resta
    scritto in `draft.scelta_da` (la squadra, o l'admin che ha scelto per lei).
    Ritorna {pick, giocatore, saltate, concluso}.
    """
    pick = _pick_valida(cur, anno, id_pick)

    if not e_admin and squadra != pick["detentore_att"]:
        raise SceltaNonValida("Non e' il turno della tua squadra.")

    # Di norma una pick senza slot e' gia' stata saltata; il controllo resta per
    # il caso in cui uno slot si sia riempito (promozione, scambio) dopo.
    if giocatori_repo.conta_primavera(cur, pick["detentore_att"]) >= SLOT_PRIMAVERA:
        raise SceltaNonValida("La squadra ha tutti gli slot Primavera occupati.")

    soglia = configurazione_repo.soglia_u21(cur)
    candidati = giocatori_repo.draftabili(cur, soglia, id_giocatore)
    if not candidati:
        raise SceltaNonValida("Il giocatore non e' draftabile: non e' un U21 svincolato.")
    giocatore = candidati[0]

    if not giocatori_repo.assegna_primavera(cur, id_giocatore, pick["detentore_att"]):
        raise SceltaNonValida("Il giocatore non risulta piu' svincolato.")
    if not draft_repo.usa_pick(cur, pick["id"], id_giocatore, da):
        raise SceltaNonValida("La pick risulta gia' usata.")

    saltate = _salta_pick_senza_slot(cur, anno)
    return {"pick": pick, "giocatore": giocatore, "saltate": saltate,
            "concluso": _chiudi_se_finito(cur, anno)}


def salta(cur, anno: int, id_pick: int, *, da: str) -> dict:
    """Salta la pick in corso (squadra assente): solo admin, lo decide la route.

    Ritorna {pick, saltate, concluso}; `saltate` comprende le pick che
    saltano a catena per slot pieni.
    """
    pick = _pick_valida(cur, anno, id_pick)
    if not draft_repo.salta_pick(cur, pick["id"], da):
        raise SceltaNonValida("La pick risulta gia' usata.")
    saltate = _salta_pick_senza_slot(cur, anno)
    return {"pick": pick, "saltate": saltate, "concluso": _chiudi_se_finito(cur, anno)}


# --- Ordine ---------------------------------------------------------------------

def anteprima_ordine(cur, anno: int) -> dict:
    """L'ordine che uscirebbe dalla classifica, senza scrivere niente.

    Ritorna {stagione, ordine, problema}: `ordine` e' [{numero, giro, squadra,
    detentore}] (detentore = chi sceglie, se la pick e' stata scambiata) oppure
    None, con `problema` che spiega perche' (classifica assente o incoerente).
    """
    stagione = stagione_della_classifica(anno)
    classifica = albo_oro_repo.classifica_campionato(cur, stagione)
    if not classifica:
        return {"stagione": stagione, "ordine": None,
                "problema": f"Manca la classifica del Campionato {stagione} nell'Albo d'oro."}
    try:
        ordine = ordine_da_classifica(classifica)
    except OrdineNonValido as e:
        return {"stagione": stagione, "ordine": None,
                "problema": f"La classifica {stagione} non e' utilizzabile: {e}"}

    detentori = {(p["giro"], p["detentore_originale"]): p["detentore_att"]
                 for p in draft_repo.pick_dell_anno(cur, anno)}
    for p in ordine:
        p["detentore"] = detentori.get((p["giro"], p["squadra"]))
    return {"stagione": stagione, "ordine": ordine, "problema": None}


def genera_ordine(cur, anno: int) -> int:
    """Scrive i numeri delle pick dalla classifica e prepara la sessione.

    Si puo' ripetere finche' il draft non e' aperto (per esempio dopo aver
    corretto la classifica nell'Albo d'oro). Ritorna il numero di pick.
    """
    sessione = sessione_repo.leggi(cur, anno)
    if sessione and sessione["stato"] != "preparato":
        raise SceltaNonValida(f"Il draft {anno} e' gia' {sessione['stato']}: l'ordine non si rigenera.")

    anteprima = anteprima_ordine(cur, anno)
    if anteprima["ordine"] is None:
        raise SceltaNonValida(anteprima["problema"])
    try:
        draft_repo.assegna_numeri(cur, anno, anteprima["ordine"])
    except ValueError as e:
        raise SceltaNonValida(str(e)) from e
    sessione_repo.prepara(cur, anno)
    return len(anteprima["ordine"])


# --- Vista ----------------------------------------------------------------------

def vista(cur, anno: int) -> dict:
    """Tutto cio' che serve a disegnare il tabellone di un draft.

    Ogni pick ha uno `stato`: scelta, saltata, in_corso (solo a draft aperto) o
    attesa. Anche a ordine non generato le pick sono elencate, senza numero.
    """
    sessione = sessione_repo.leggi(cur, anno)
    pick = draft_repo.pick_con_dettagli(cur, anno)
    in_corso = draft_repo.pick_in_corso(cur, anno) if sessione and sessione["stato"] == "aperto" else None
    for p in pick:
        p["ruolo"] = pulisci_ruolo(p["ruolo"])
        if p["giocatore"]:
            p["stato"] = "scelta"
        elif p["saltata"]:
            p["stato"] = "saltata"
        elif in_corso and p["id"] == in_corso["id"]:
            p["stato"] = "in_corso"
        else:
            p["stato"] = "attesa"
    # L'ultima scelta fatta, per l'animazione della pagina live. L'eta' e' calcolata
    # dal database (now() - scelta_il) e non dal browser: gli orologi dei telefoni
    # sono sfasati, e un anticipo o un ritardo farebbe saltare o ripetere l'animazione.
    scelte = [p for p in pick if p["stato"] == "scelta" and p["scelta_il"] is not None]
    ultima_scelta = max(scelte, key=lambda p: p["scelta_il"]) if scelte else None
    return {"anno": anno, "sessione": sessione, "pick": pick, "in_corso": in_corso,
            "ultima_scelta": ultima_scelta,
            "ha_ordine": any(p["numero"] is not None for p in pick)}


def pool(cur) -> list[dict]:
    """Gli svincolati che si possono scegliere al draft, per l'elenco della pagina."""
    return [{**g, "ruolo": pulisci_ruolo(g["ruolo"])}
            for g in giocatori_repo.draftabili(cur, configurazione_repo.soglia_u21(cur))]


def riepilogo(cur, anno: int) -> dict[str, list[str]]:
    """{squadra: [giocatori scelti]} di un draft, per la comunicazione finale."""
    per_squadra: dict[str, list[str]] = {}
    for p in sorted(draft_repo.pick_con_dettagli(cur, anno), key=lambda p: p["numero"] or 0):
        if p["giocatore"]:
            per_squadra.setdefault(p["detentore_att"], []).append(p["giocatore"])
    return per_squadra
