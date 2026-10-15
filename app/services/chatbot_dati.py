"""
Dati live della lega per il chatbot: gli strumenti che il modello puo' chiamare.

Il regolamento da solo non basta a rispondere a "quanti crediti ha X?" o "posso
tagliare Y?": qui il modello trova, in sola lettura, le stesse informazioni che
le pagine pubbliche gia' mostrano a chiunque (listone, rose, movimenti, albo
d'oro). Nessuno strumento scrive: il chatbot non e' dietro login.

Ogni strumento apre la propria connessione e la rilascia subito. Tenerne una
per tutta la conversazione la occuperebbe anche durante l'attesa del modello,
che dura secondi, sottraendola al pool delle pagine.
"""

import json

from app.core.db import connessione
from app.core.logging import get_logger
from app.core.tempo import calcola_eta
from app.domini.ruoli import pulisci_ruolo
from app.repositories import albo_oro as albo_oro_repo
from app.repositories import aste as aste_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import movimenti as movimenti_repo
from app.repositories import squadre as squadre_repo
from app.repositories import stadio as stadio_repo
from app.services import dashboard as dashboard_service
from app.services import rosa as rosa_service

logger = get_logger(__name__)

# Un movimento e' testo libero e alcuni sono lunghi: oltre questo numero il
# contesto del modello si riempie di storia che nessuno ha chiesto.
MOVIMENTI_MAX = 20

STRUMENTI = [
    {"type": "function", "function": {
        "name": "panoramica_squadre",
        "description": "Per ogni squadra della lega: crediti, slot occupati in rosa (max 30), "
                       "prestiti in entrata (max 2) e livello dello stadio.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "scheda_squadra",
        "description": "Scheda completa di una squadra: crediti, stadio, rosa con ruoli/quotazioni/"
                       "costi, primavera, prestiti in entrata e in uscita, pick del draft, palmares.",
        "parameters": {"type": "object", "properties": {
            "squadra": {"type": "string", "description": "Nome della squadra"}},
            "required": ["squadra"]},
    }},
    {"type": "function", "function": {
        "name": "cerca_giocatore",
        "description": "Cerca giocatori per nome. I nomi sono nel formato di Fantacalcio.it, "
                       "cioe' il cognome seguito a volte dall'iniziale (es. 'Martinez L.' per "
                       "Lautaro Martinez): cerca per cognome, non per nome di battesimo o "
                       "soprannome. Dice in che squadra sono, contratto, quotazione, costo, eta', "
                       "valore di mercato e da quando si possono tagliare.",
        "parameters": {"type": "object", "properties": {
            "nome": {"type": "string", "description": "Cognome (o parte) del giocatore"}},
            "required": ["nome"]},
    }},
    {"type": "function", "function": {
        "name": "movimenti",
        "description": "Ultimi movimenti di mercato (scambi, prestiti, tagli, cessioni), dal piu' "
                       "recente. Con `squadra` solo quelli che la riguardano.",
        "parameters": {"type": "object", "properties": {
            "squadra": {"type": "string", "description": "Facoltativo: nome della squadra"}}},
    }},
    {"type": "function", "function": {
        "name": "aste_attive",
        "description": "Aste in corso e giocatori per cui si sta raccogliendo interesse, con "
                       "offerta attuale, squadra in vantaggio e scadenza.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "albo_oro",
        "description": "Albo d'oro: piazzamenti di Campionato e Coppa per stagione.",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "stato_mercato",
        "description": "Se mercato e aste sono aperti, le date di chiusura e l'anno di nascita "
                       "da cui un giocatore conta come U21.",
        "parameters": {"type": "object", "properties": {}},
    }},
]


def risolvi_squadra(richiesta: str, nomi: list[str]) -> str | None:
    """Il nome esatto della squadra a partire da come l'utente l'ha scritto.

    Il modello passa il nome come lo ha letto nella domanda, quindi spesso in
    minuscolo o abbreviato. Prima l'uguaglianza senza maiuscole, poi il
    contenimento, ma solo se porta a una squadra sola: indovinare fra due
    sarebbe peggio che chiedere.
    """
    cercato = (richiesta or "").strip().lower()
    if not cercato:
        return None
    for nome in nomi:
        if nome.lower() == cercato:
            return nome
    candidati = [n for n in nomi if cercato in n.lower() or n.lower() in cercato]
    return candidati[0] if len(candidati) == 1 else None


def _squadra_o_errore(cur, richiesta):
    nomi = squadre_repo.nomi(cur)
    nome = risolvi_squadra(richiesta, nomi)
    if nome is None:
        return None, {"errore": f"Squadra '{richiesta}' non trovata.", "squadre_esistenti": nomi}
    return nome, None


def _giocatore(g: dict) -> dict:
    """Solo i campi utili a rispondere, senza quelli che servono alla pagina
    (loghi, campioncini, id)."""
    return {
        "nome": g["nome"],
        "ruolo": g["ruolo"],
        "club": g["club"],
        "contratto": g["tipo_contratto"],
        "quotazione": g["quot_att_mantra"],
        "costo": g["costo"],
    }


def _panoramica_squadre(cur, _args):
    slot = giocatori_repo.slot_per_squadra(cur)
    stadi = {s["proprietario"]: s["livello"] for s in stadio_repo.elenco(cur)}
    return [{
        "squadra": s["nome"],
        "crediti": s["crediti"],
        "slot_occupati": slot.get(s["nome"], {}).get("giocatori", 0),
        "prestiti_in_entrata": slot.get(s["nome"], {}).get("prestiti", 0),
        "livello_stadio": stadi.get(s["nome"]),
    } for s in squadre_repo.nomi_e_crediti(cur)]


def _scheda_squadra(cur, args):
    nome, errore = _squadra_o_errore(cur, args.get("squadra"))
    if errore:
        return errore
    dati = dashboard_service.dati_squadra(cur, nome)
    titoli = dati["palmares"]
    return {
        "squadra": nome,
        "crediti": dati["crediti"],
        "stadio": dati["stadio"],
        "slot_occupati": dati["slot_occupati"],
        "eta_media": dati["eta_media"],
        "valore_rosa": dati["valore_rosa_totale"],
        # La rosa della pagina comprende anche i prestiti in entrata, che qui
        # hanno gia' un elenco loro: ripeterli confonderebbe i conteggi.
        "rosa": [_giocatore(g) for g in dati["rosa"] if g["tipo_contratto"] != "Fanta-Prestito"],
        "primavera": [_giocatore(g) for g in dati["primavera"]],
        "prestiti_in_entrata": [{**_giocatore(g), "proprietario": g["detentore_cartellino"]}
                                for g in dati["prestiti_in"]],
        "prestiti_in_uscita": [{**_giocatore(g), "dove": g["squadra_att"]}
                               for g in dati["prestiti_out"]],
        "pick_draft": [{"anno": p["anno"], "numero": p["numero"],
                        "originale_di": p["detentore_originale"],
                        "giocatore_scelto": p["giocatore_scelto"]} for p in dati["draft_pick"]],
        "palmares": titoli,
    }


def _cerca_giocatore(cur, args):
    testo = (args.get("nome") or "").strip()
    if len(testo) < 3:
        return {"errore": "Servono almeno 3 lettere del nome."}
    righe = giocatori_repo.cerca_per_nome(cur, testo)
    if not righe:
        return {"errore": f"Nessun giocatore con '{testo}' nel nome."}
    bloccati = rosa_service.tagliabili_dal(cur, [g["id"] for g in righe])
    risultato = []
    for g in righe:
        voce = {
            **_giocatore(g),
            "ruolo": pulisci_ruolo(g["ruolo"]),
            "squadra": g["squadra_att"],
            "cartellino_di": g["detentore_cartellino"],
            "eta": calcola_eta(g["data_nascita"]),
            "scadenza_contratto_reale": g["scadenza_contratto"],
            "valore_mercato_euro": g["valore_mercato"],
        }
        # Il vincolo dei 4 mesi vale solo per la prima squadra: dalla Primavera
        # il taglio e' sempre libero.
        if g["id"] in bloccati and g["tipo_contratto"] != "Primavera":
            voce["tagliabile_dal"] = bloccati[g["id"]]
        risultato.append(voce)
    return risultato


def _movimenti(cur, args):
    if args.get("squadra"):
        nome, errore = _squadra_o_errore(cur, args["squadra"])
        if errore:
            return errore
        righe = movimenti_repo.per_squadra(cur, nome)
    else:
        righe = movimenti_repo.tutti(cur)
    return [{"data": m["data"], "evento": m["evento"]} for m in righe[:MOVIMENTI_MAX]]


def _aste_attive(cur, _args):
    return [{
        "giocatore": a["nome"],
        "ruolo": pulisci_ruolo(a["ruolo"]),
        "club": a["club"],
        "stato": a["stato"],
        "offerta_attuale": a["ultima_offerta"],
        "in_vantaggio": a["squadra_vincente"],
        "partecipanti": a["partecipanti"],
        "fine_interesse": a["tempo_fine_mostra_interesse"],
        "fine_asta": a["tempo_fine_asta"],
    } for a in aste_repo.elenco_completo(cur) if a["stato"] in ("mostra_interesse", "in_corso")]


def _albo_oro(cur, _args):
    return [{
        "stagione": r["stagione"],
        "competizione": r["competizione"],
        "fase": r["fase"],
        "posizione": r["posizione"],
        "squadra": r["squadra"],
    } for r in albo_oro_repo.leggi(cur)]


def _stato_mercato(cur, _args):
    return configurazione_repo.stato_gate(cur)


_ESECUTORI = {
    "panoramica_squadre": _panoramica_squadre,
    "scheda_squadra": _scheda_squadra,
    "cerca_giocatore": _cerca_giocatore,
    "movimenti": _movimenti,
    "aste_attive": _aste_attive,
    "albo_oro": _albo_oro,
    "stato_mercato": _stato_mercato,
}


def esegui(nome: str, argomenti_json: str | None) -> str:
    """Esegue uno strumento e restituisce il risultato come JSON per il modello.

    Mai un'eccezione verso il chiamante: un errore diventa un messaggio che il
    modello puo' leggere e riferire, invece di far fallire tutta la risposta.
    """
    esecutore = _ESECUTORI.get(nome)
    if esecutore is None:
        return json.dumps({"errore": f"Strumento '{nome}' inesistente."})
    try:
        argomenti = json.loads(argomenti_json or "{}") or {}
        if not isinstance(argomenti, dict):
            argomenti = {}
    except json.JSONDecodeError:
        argomenti = {}
    try:
        with connessione() as (_conn, cur):
            risultato = esecutore(cur, argomenti)
    except Exception:
        logger.exception("Chatbot: errore nello strumento %s", nome)
        return json.dumps({"errore": "Dati non disponibili in questo momento."})
    # default=str: date, Decimal e simili arrivano dal database cosi' come sono.
    return json.dumps(risultato, ensure_ascii=False, default=str)


def nomi_squadre() -> list[str]:
    """Per il prompt di sistema: sapere quali squadre esistono evita al modello
    di chiamare uno strumento con un nome inventato. Vuoto se il database non
    risponde, il chatbot sul regolamento deve funzionare lo stesso."""
    try:
        with connessione() as (_conn, cur):
            return squadre_repo.nomi(cur)
    except Exception:
        logger.exception("Chatbot: impossibile leggere i nomi delle squadre")
        return []
