"""
Funzioni pure di matching tra i giocatori di `giocatore` e l'elenco scaricato
dalla pagina quotazioni di fantacalcio.it. Nessun accesso a DB o rete qui.

A differenza del matching Transfermarkt (vedi
app/domini/matching_transfermarkt.py) qui il nome del giocatore nel nostro DB
arriva già dal listone di fantacalcio.it: non serve confrontare solo il
cognome con uno scoping per club, il nome intero normalizzato è già la stessa
stringa nella stragrande maggioranza dei casi.
"""

import unicodedata

# Valore di giocatore.id_fantacalcio per "l'admin ha verificato che su
# fantacalcio.it non c'e'": distinto da NULL (mai cercato o ancora da
# abbinare), cosi' la sincronizzazione non lo rimette in coda ogni giorno.
# Non e' definitivo: se piu' avanti nel listone compare un unico giocatore
# con stesso nome e stesso club, viene abbinato lo stesso (vedi
# app/services/fantacalcio.py). Un id vero e' sempre positivo;
# url_campioncino tratta questo valore come "nessun campioncino".
NESSUNA_CORRISPONDENZA = -1

# Club il cui nome non comincia con la sigla a 3 lettere che usa
# fantacalcio.it (per tutti gli altri la sigla e' semplicemente l'inizio del
# nome: Milan -> MIL, Torino -> TOR, ...).
_SIGLE_SPECIALI = {
    "hellas verona": "VER",
}

# Lettere che NFKD non decompone in ASCII, stessa tabella di
# matching_transfermarkt.py (duplicata invece che importata: i due moduli
# restano indipendenti, stesso principio dei domini negli altri file).
TRANSLIT = str.maketrans({
    "ı": "i", "İ": "i",
    "ł": "l", "Ł": "l",
    "ø": "o", "Ø": "o",
    "đ": "d", "Đ": "d",
    "ß": "ss",
})


def normalizza(testo):
    """Minuscolo, senza accenti/punteggiatura, per confronti robusti sui nomi."""
    if not testo:
        return ""
    testo = testo.translate(TRANSLIT)
    testo = unicodedata.normalize("NFKD", testo).encode("ascii", "ignore").decode("ascii")
    return "".join(c for c in testo.lower() if c.isalnum() or c.isspace()).strip()


def candidati_esatti(nome_db: str, giocatori_fc: list[dict]) -> list[dict]:
    """Nome normalizzato uguale. Il listone di questa app viene già da
    fantacalcio.it, quindi qui basta il confronto sul nome intero: se dà
    esattamente 1 risultato è sicuro abbastanza da salvare senza revisione.
    """
    cercato = normalizza(nome_db)
    return [g for g in giocatori_fc if normalizza(g["nome"]) == cercato]


def sigla_club(club: str) -> str:
    """La sigla fantacalcio.it (es. "MIL") di un club di questa app."""
    chiave = normalizza(club)
    return _SIGLE_SPECIALI.get(chiave, chiave.replace(" ", "")[:3].upper())


def candidati_stesso_club(nome_db: str, club_db: str, giocatori_fc: list[dict]) -> list[dict]:
    """Nome normalizzato uguale e stesso club.

    Per i giocatori che secondo il nostro DB non sono nel listone (priorita
    0): un omonimo nel listone potrebbe essere un'altra persona, quindi il
    solo nome non basta a fidarsi senza revisione. Con anche il club uguale
    si': e' lo stesso giocatore, la priorita' e' solo rimasta indietro.
    """
    if not club_db:
        return []
    sigla = sigla_club(club_db)
    return [g for g in candidati_esatti(nome_db, giocatori_fc)
            if (g.get("squadra_fc") or "").upper() == sigla]
