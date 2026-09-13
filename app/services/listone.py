"""
Composizione del listone.

La pagina elenca oltre cinquecento giocatori, e ogni riga portava con se' un
attributo JSON con i tredici campi che servono alla scheda di dettaglio, aperta
solo quando si clicca la riga. I dati viaggiavano quindi cinquecento volte, e
con essi i nomi dei campi ripetuti ogni volta: circa cento kilobyte di sole
chiavi.

Qui gli stessi dati diventano una tabella compatta - i nomi dichiarati una
volta, poi una riga di valori per giocatore - che viaggia in un blocco unico in
fondo alla pagina.
"""

from app.core.formato import formatta_valore_mercato_mln
from app.core.tempo import (formatta_data_nascita_con_eta,
                            formatta_scadenza_contratto)
from app.domini.ruoli import pulisci_ruolo, ruoli_base_presenti
from app.repositories import configurazione as configurazione_repo
from app.repositories import giocatori as giocatori_repo

NON_SINCRONIZZATA = "Non sincronizzata"
NON_SINCRONIZZATO = "Non sincronizzato"

# I campi che la scheda di dettaglio mostra, nell'ordine in cui viaggiano.
# Il template li rilegge da qui: aggiungerne uno basta a farlo arrivare.
CAMPI_SCHEDA = (
    "nome", "ruolo", "club", "squadra_att", "squadra_username",
    "detentore", "detentore_username", "tipo_contratto",
    "quotazione", "costo", "data_nascita", "scadenza_contratto_reale",
    "valore_mercato",
)

# Nella scheda il detentore del cartellino si chiama solo "detentore": e'
# l'unico nome che cambia fra riga e scheda, e la corrispondenza sta qui.
NOMI_DIVERSI_NELLA_SCHEDA = {"detentore": "detentore_cartellino"}


def stato_u21(data_nascita, soglia_u21) -> str:
    """'si'/'no' per il filtro del listone, '' quando non e' determinabile.

    Sono U21 i nati nell'anno di soglia o dopo, stessa regola delle aste. Senza
    soglia impostata o senza data di nascita sincronizzata non si puo' dire, e
    il filtro deve lasciar passare il giocatore invece di escluderlo.
    """
    if soglia_u21 is None or data_nascita is None:
        return ""
    return "si" if data_nascita.year >= soglia_u21 else "no"


def _riga(g: dict, soglia_u21) -> dict:
    return {
        "nome": g["nome"],
        "ruolo": pulisci_ruolo(g["ruolo"]),
        "club": g["club"],
        "squadra_att": g["squadra_att"],
        "squadra_username": g["squadra_username"],
        "detentore_cartellino": g["detentore_cartellino"],
        "detentore_username": g["detentore_username"],
        "tipo_contratto": g["tipo_contratto"],
        "quotazione": g["quot_att_mantra"],
        "costo": g["costo"],
        "data_nascita": formatta_data_nascita_con_eta(g["data_nascita"]) or NON_SINCRONIZZATA,
        "scadenza_contratto_reale": formatta_scadenza_contratto(g["scadenza_contratto"]) or NON_SINCRONIZZATA,
        "valore_mercato": formatta_valore_mercato_mln(g["valore_mercato"]) or NON_SINCRONIZZATO,
        "u21": stato_u21(g["data_nascita"], soglia_u21),
    }


def _dati_scheda(giocatori: list[dict]) -> dict:
    """I valori per la scheda di dettaglio, senza ripetere i nomi dei campi."""
    def valore(g, campo):
        return g[NOMI_DIVERSI_NELLA_SCHEDA.get(campo, campo)]

    return {
        "campi": list(CAMPI_SCHEDA),
        "righe": [[valore(g, c) for c in CAMPI_SCHEDA] for g in giocatori],
    }


def dati_pagina(cur) -> dict:
    soglia_u21 = configurazione_repo.soglia_u21(cur)
    giocatori = [_riga(g, soglia_u21) for g in giocatori_repo.listone(cur)]

    return {
        "giocatori": giocatori,
        "dati_scheda": _dati_scheda(giocatori),
        "ruoli_disponibili": ruoli_base_presenti([g["ruolo"] for g in giocatori]),
        "club_disponibili": sorted({g["club"] for g in giocatori if g["club"]}),
        "squadre_disponibili": sorted({g["squadra_att"] for g in giocatori if g["squadra_att"]}),
        "contratti_disponibili": sorted({g["tipo_contratto"] for g in giocatori if g["tipo_contratto"]}),
        "u21_threshold_year": soglia_u21,
    }
