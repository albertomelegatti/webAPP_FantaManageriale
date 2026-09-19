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
