"""
Pagina crediti/stadi/slot: crediti, occupazione della rosa e stadio di ogni
squadra, in una riga per squadra da cui il template ricava le due tabelle.

La tabella degli slot nascondeva le squadre senza giocatori sotto contratto:
qui ci sono sempre tutte.
"""

from app.repositories import giocatori as giocatori_repo
from app.repositories import squadre as squadre_repo
from app.repositories import stadio as stadio_repo

# Limiti di rosa dal regolamento (3.2 e 3.4).
SLOT_ROSA = 30
SLOT_PRESTITI = 2

# Rendita annuale per livello di stadio, dal regolamento (sezione 4). E' il
# valore di partenza: l'admin la modifica dalla pagina Stadi e il valore in uso
# sta nella tabella stadio_livello (vedi rendite_in_uso). Questa tupla serve
# solo finche' la tabella non e' stata creata.
RENDITA_STADIO = (0, 4, 8, 14, 18, 25, 30, 39, 44)


def rendite_in_uso(cur) -> list[int]:
    """Le rendite per livello correnti: quelle salvate, o il default."""
    return stadio_repo.rendite(cur) or list(RENDITA_STADIO)


def rendita_stadio(rendite, livello) -> int:
    if livello is None or not 0 <= livello < len(rendite):
        return 0
    return rendite[livello]


def rendite_da_accreditare(squadre: list[dict], rendite) -> list[tuple[str, int]]:
    """(squadra, crediti) per le squadre con uno stadio che rende qualcosa.

    `squadre` e' l'elenco di squadre_repo.tutte_con_stadio(). Una squadra senza
    stadio, o con uno stadio di livello 0, non riceve nulla.
    """
    accrediti = []
    for s in squadre:
        crediti = rendita_stadio(rendite, s["stadio_livello"])
        if crediti > 0:
            accrediti.append((s["nome"], crediti))
    return accrediti


def dati_pagina(cur) -> dict:
    slot = giocatori_repo.slot_per_squadra(cur)
    rendite = rendite_in_uso(cur)

    squadre = []
    for s in squadre_repo.tutte_con_stadio(cur):
        occupazione = slot.get(s["nome"], {})
        squadre.append({
            "nome": s["nome"],
            "username": s["username"],
            "crediti": s["crediti"],
            "slot_occupati": occupazione.get("giocatori", 0),
            "prestiti": occupazione.get("prestiti", 0),
            "stadio_nome": s["stadio_nome"],
            "stadio_livello": s["stadio_livello"],
            "rendita": rendita_stadio(rendite, s["stadio_livello"]),
        })

    # Ordine iniziale per crediti: la pagina si apre sulla domanda che le si
    # fa piu' spesso, "chi ha piu' crediti?".
    squadre.sort(key=lambda s: (-s["crediti"], s["nome"]))

    return {
        "squadre": squadre,
        "slot_rosa": SLOT_ROSA,
        "slot_prestiti": SLOT_PRESTITI,
    }
