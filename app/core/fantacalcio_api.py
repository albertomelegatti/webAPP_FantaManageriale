"""
Client per la pagina quotazioni di fantacalcio.it: l'id di ogni giocatore
serve per mostrare il suo campioncino ufficiale (la card), scaricabile da
https://content.fantacalcio.it/web/campioncini/<stagione>/card/<id>.png.

A differenza di Transfermarkt (vedi app/core/transfermarkt_api.py, che usa uno
scraper esterno in più comandi) qui la pagina è un'unica tabella
server-renderizzata con l'intero listone di Serie A (~600 giocatori, niente
paginazione né caricamento via JS): una sola richiesta HTTP basta, nessun
sottoprocesso necessario.
"""

import html
import re

import requests

from app.core.logging import get_logger

logger = get_logger(__name__)

_URL_QUOTAZIONI = "https://www.fantacalcio.it/quotazioni-fantacalcio"
_UA = "webapp-fantamanageriale (+https://webapp-fantamanageriale.onrender.com)"
_HEADERS = {"User-Agent": _UA}

# Un giocatore è un link al suo profilo (con l'id in fondo all'URL) seguito,
# poco dopo nello stesso markup della riga, dalla sigla a 3 lettere della
# squadra. Regex e non un parser HTML vero perché la pagina non ha altre
# dipendenze in questo progetto e la struttura è stabile e ripetitiva.
_RIGA_RE = re.compile(
    r'squadre/[^/"]+/[^/"]+/(?P<id>\d+)"[^>]*>\s*<span>(?P<nome>[^<]+)</span>\s*</a>'
    r'.*?class="player-team"[^>]*>\s*(?P<squadra>[A-Za-z]{2,4})\s*<',
    re.DOTALL,
)


def scarica_quotazioni() -> list[dict]:
    """Tutti i giocatori della pagina quotazioni: [{"id_fantacalcio", "nome",
    "squadra_fc"}, ...].

    Solleva `requests.HTTPError` se la richiesta fallisce: chi chiama non deve
    mai proseguire con una pagina non scaricata (vedi la soglia minima in
    app/repositories/fantacalcio.py, stesso principio della soglia Transfermarkt).
    """
    risposta = requests.get(_URL_QUOTAZIONI, headers=_HEADERS, timeout=20)
    risposta.raise_for_status()

    # I nomi arrivano con entity HTML numeriche per gli accentati
    # (es. "Kessi&#xE8;" invece di "Kessiè"): senza html.unescape() il
    # confronto sul nome normalizzato fallisce per ogni giocatore accentato.
    giocatori = [
        {
            "id_fantacalcio": int(m.group("id")),
            "nome": html.unescape(m.group("nome")).strip(),
            "squadra_fc": m.group("squadra").strip(),
        }
        for m in _RIGA_RE.finditer(risposta.text)
    ]

    # Lo stesso giocatore può comparire più volte nel markup (es. blocchi
    # ruolo sovrapposti): l'id è lo stesso, l'ultima occorrenza vince.
    per_id = {g["id_fantacalcio"]: g for g in giocatori}
    return list(per_id.values())
