"""
Client per l'API pubblica dei valori di mercato di Transfermarkt.

Lo scraper (transfermarkt-scraper) non estrae più il valore di mercato dalla
pagina HTML del giocatore: il markup di quella sezione è cambiato e la sua xpath
non aggancia più nulla (stessa causa dei WARN "Failed to scrape market value
history"). L'endpoint JSON /ceapi/marketValueDevelopment/graph/<id> invece dà lo
storico completo delle valutazioni in forma stabile, ed è quello che usa anche
l'autore dello scraper nel suo progetto transfermarkt-datasets.

Strategia per richiesta: prima diretta, poi — solo se la diretta viene bloccata
(DataDome) — fallback su Bright Data Web Unlocker, con le stesse variabili
d'ambiente già usate dallo scraper (BRIGHTDATA_API_KEY, BRIGHTDATA_ZONE). Su un
IP datacenter come Render la diretta viene bloccata spesso, quindi in pratica
passa quasi tutto dall'unlocker.

Un valore non recuperato resta None: chi chiama non deve mai sovrascrivere con
None un valore già salvato (vedi scripts/match_transfermarkt.py).
"""

import concurrent.futures
import os
import threading

import requests

from app.core.logging import get_logger
from app.domini.matching_transfermarkt import valore_mercato_da_ceapi

logger = get_logger(__name__)

_CEAPI_URL = "https://www.transfermarkt.com/ceapi/marketValueDevelopment/graph/{id}"
_BRIGHTDATA_ENDPOINT = "https://api.brightdata.com/request"

# Segnature di blocco misurate: le stesse su cui lo scraper fa fallback.
_STATUS_BLOCCATO = {202, 403, 405, 429}
_MARCATORI_DATADOME = (b"datadome", b"captcha-delivery", b"human verification")

_UA = "webapp-fantamanageriale (+https://webapp-fantamanageriale.onrender.com)"
_HEADERS = {"User-Agent": _UA, "Accept": "application/json"}

_MAX_WORKER = 12
_TIMEOUT_DIRETTO = 15
_TIMEOUT_UNLOCKER = 120

# Sotto questa quota di successi il run ha con ogni probabilità sbattuto contro
# un blocco di massa: si logga un warning, ma NON si fallisce (chi chiama non
# sovrascrive comunque i valori già a DB con i None).
_QUOTA_MINIMA_SUCCESSI = 0.5

_locale = threading.local()


def _sessione():
    """Una requests.Session per thread: le Session non sono thread-safe."""
    sessione = getattr(_locale, "sessione", None)
    if sessione is None:
        sessione = _locale.sessione = requests.Session()
    return sessione


def _sembra_bloccata(risposta):
    if risposta.status_code in _STATUS_BLOCCATO:
        return True
    corpo = risposta.content[:4096].lower()
    return any(m in corpo for m in _MARCATORI_DATADOME)


def _tramite_brightdata(url):
    api_key = os.getenv("BRIGHTDATA_API_KEY")
    if not api_key:
        return None
    zona = os.getenv("BRIGHTDATA_ZONE") or "web_unlocker2"
    try:
        risposta = _sessione().post(
            _BRIGHTDATA_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"zone": zona, "url": url, "format": "raw"},
            timeout=_TIMEOUT_UNLOCKER,
        )
        return risposta.json()
    except (requests.RequestException, ValueError):
        return None


def _valore_di(id_transfermarkt):
    """Valore di mercato in euro per un id, o None se non recuperabile."""
    url = _CEAPI_URL.format(id=id_transfermarkt)

    try:
        risposta = _sessione().get(url, headers=_HEADERS, timeout=_TIMEOUT_DIRETTO)
        if risposta.status_code == 200 and not _sembra_bloccata(risposta):
            try:
                return valore_mercato_da_ceapi(risposta.json())
            except ValueError:
                pass  # 200 ma non JSON: soft-block, si prova l'unlocker
        elif 400 <= risposta.status_code < 500 and risposta.status_code not in _STATUS_BLOCCATO:
            return None  # 404 & co.: la pagina non esiste, inutile insistere
    except requests.RequestException:
        pass

    payload = _tramite_brightdata(url)
    if payload is None:
        return None
    return valore_mercato_da_ceapi(payload)


def recupera_valori_mercato(id_transfermarkt):
    """{id_transfermarkt: valore_in_euro_o_None} per gli id passati.

    Recupera in parallelo. Non solleva mai: gli id non risolti finiscono a None.
    """
    ids = sorted({int(i) for i in id_transfermarkt if i})
    if not ids:
        return {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=_MAX_WORKER) as pool:
        valori = list(pool.map(_valore_di, ids))
    risultati = dict(zip(ids, valori))

    n_ok = sum(1 for v in risultati.values() if v is not None)
    quota = n_ok / len(ids)
    if quota < _QUOTA_MINIMA_SUCCESSI:
        logger.warning(
            "Valori di mercato Transfermarkt: solo %d/%d recuperati (%.0f%%): "
            "probabile blocco. I valori già a DB restano invariati.",
            n_ok, len(ids), quota * 100,
        )
    else:
        logger.info("Valori di mercato Transfermarkt: %d/%d recuperati.", n_ok, len(ids))
    return risultati
