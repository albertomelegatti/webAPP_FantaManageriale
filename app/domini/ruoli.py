"""
Ruoli Mantra: ordinamento e normalizzazione.

Funzioni pure, nessun accesso a database o rete: dipendono solo dai loro
argomenti e sono quindi testabili senza alcuna infrastruttura.
"""

# Stesso ordine di ruoli già usato in produzione (vedi static/js/tables.js,
# RUOLO_PRIORITY): portieri, poi difensori, centrocampisti, esterni/trequartisti,
# infine attaccanti.
RUOLO_PRIORITY = {
    'POR': 1,
    'DD,E': 2,
    'DD,DC': 3,
    'DC': 4,
    'DD,DS,DC': 5,
    'DS,DC': 6,
    'DS,E': 7,
    'B,DD,E': 8,
    'B,DD,DS': 9,
    'B,DS,E': 10,
    'DD,DS,E': 11,
    'M,C': 12,
    'E': 13,
    'E,M': 14,
    'E,C': 15,
    'E,W': 16,
    'C,T': 17,
    'C': 18,
    'C,W,T': 19,
    'C,W': 20,
    'W': 21,
    'W,T': 22,
    'W,A': 23,
    'W,T,A': 24,
    'T,A': 25,
    'T': 26,
    'A': 27,
    'PC': 28,
}

# Ordine dei ruoli base (singoli), stesso ordine POR -> difesa -> centrocampo
# -> esterni/trequartisti -> attacco usato per colorarli (vedi _macros.html)
RUOLI_BASE_ORDINE = ['Por', 'Dd', 'Ds', 'Dc', 'B', 'E', 'M', 'C', 'W', 'T', 'A', 'Pc']

# Posizione assegnata a un ruolo non riconosciuto: finisce in fondo all'ordinamento.
POSIZIONE_SCONOSCIUTO = 99


def pulisci_ruolo(ruolo_grezzo: str | None) -> str:
    """'{DC,DD}' -> 'DC,DD'.

    Il campo `ruolo` è un array PostgreSQL e psycopg2 lo restituisce come
    stringa con le graffe. Questa conversione era ripetuta a mano in 21 punti
    del codice, in due varianti (con e senza protezione dal valore nullo).
    """
    return (ruolo_grezzo or "").strip("{}")


def ruolo_sort_key(ruolo: str) -> int:
    chiave = ruolo.strip().upper().replace(' ', '')
    return RUOLO_PRIORITY.get(chiave, POSIZIONE_SCONOSCIUTO)


def ruolo_base_sort_key(ruolo: str) -> int:
    try:
        return RUOLI_BASE_ORDINE.index(ruolo)
    except ValueError:
        return POSIZIONE_SCONOSCIUTO


def ruoli_base_presenti(ruoli: list[str]) -> list[str]:
    """Insieme ordinato dei ruoli base che compaiono in un elenco di ruoli
    composti: ['DD,E', 'C'] -> ['Dd', 'E', 'C'] nell'ordine di campo.

    Serve a costruire i filtri per ruolo di listone e vetrina, dove la stessa
    scomposizione era scritta due volte.
    """
    base = set()
    for ruolo in ruoli:
        for token in (ruolo or "").split(","):
            token = token.strip()
            if token:
                base.add(token)
    return sorted(base, key=ruolo_base_sort_key)
