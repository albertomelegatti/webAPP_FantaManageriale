"""
Funzioni pure di matching tra i giocatori di `giocatore` e i profili scaricati
da Transfermarkt. Nessun accesso a DB o rete qui: condiviso tra
scripts/match_transfermarkt.py (che scrive i match) e admin.py (che calcola
al volo i suggerimenti fuzzy da mostrare nella pagina di revisione, senza
persisterli finché l'admin non li conferma).
"""

import unicodedata
from datetime import datetime

# Lettere che NFKD non decompone in ASCII (non sono lettera+accento separabili,
# es. la ı turca di 'Yıldız'): senza questa tabella finiscono cancellate invece
# che trascritte, e il match sul cognome fallisce silenziosamente.
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


def cognome_e_iniziale(nome_db):
    """
    'Moro L.' -> ('moro', 'l'); 'Ambrosino' -> ('ambrosino', None).
    Il nome nel nostro DB è sempre 'Cognome' o 'Cognome I.' (iniziale disambiguante,
    non sempre una sola lettera: es. 'Esposito Se.').
    """
    parti = nome_db.strip().rsplit(" ", 1)
    if len(parti) == 2 and parti[1].endswith("."):
        return normalizza(parti[0]), normalizza(parti[1].rstrip("."))
    return normalizza(nome_db), None


def parse_data_tm(testo):
    """'01/07/2000' -> date(2000, 7, 1). None/'-' -> None."""
    if not testo or testo.strip() in ("", "-"):
        return None
    try:
        return datetime.strptime(testo.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _filtra_per_iniziale(candidati, iniziale):
    if iniziale and len(candidati) > 1:
        filtrati = [g for g in candidati if normalizza(g["nome"]).startswith(iniziale)]
        if filtrati:
            return filtrati
    return candidati


def candidati_esatti(nome_db, giocatori_tm_del_club):
    """Cognome normalizzato uguale, parola per parola. Alta precisione: se dà
    esattamente 1 risultato è sicuro abbastanza da salvare senza revisione."""
    cognome, iniziale = cognome_e_iniziale(nome_db)
    candidati = [g for g in giocatori_tm_del_club if normalizza(g["cognome"]) == cognome]
    return _filtra_per_iniziale(candidati, iniziale)


def candidati_fuzzy(nome_db, giocatori_tm_del_club):
    """
    Match più permissivo, a token: usato solo come suggerimento quando il match
    esatto non trova nulla (es. cognomi composti troncati in modo diverso tra
    il nostro DB e Transfermarkt: 'Oulai' vs 'Inao Oulaï', 'Zambo Anguissa' vs
    'Anguissa'). Va sempre e solo mostrato in revisione, mai salvato da solo:
    su cognomi corti un token in comune non è una prova sufficiente.
    """
    cognome, iniziale = cognome_e_iniziale(nome_db)
    token_nostri = set(cognome.split())
    candidati = [
        g for g in giocatori_tm_del_club
        if token_nostri & set(normalizza(g["cognome"]).split())
    ]
    return _filtra_per_iniziale(candidati, iniziale)
