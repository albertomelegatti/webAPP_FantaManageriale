"""
Composizione del listone.

La pagina elenca oltre cinquecento giocatori, e il server ne mandava l'HTML
completo: cinquecento righe di tabella, ognuna con un attributo JSON che
ripeteva i nomi dei tredici campi della scheda di dettaglio. Il browser doveva
costruirle tutte prima di mostrare qualcosa, anche se ne restano visibili
venticinque.

Qui il server manda solo i dati, in forma compatta: i nomi dei campi dichiarati
una volta, poi una riga di valori per giocatore. Le righe della tabella le
disegna il browser, una pagina alla volta (vedi static/js/listone.js).
"""

from app.core.formato import formatta_valore_mercato_mln
from app.core.tempo import (formatta_data_nascita_con_eta,
                            formatta_scadenza_contratto)
from app.domini.ruoli import pulisci_ruolo, ruoli_base_presenti
from app.repositories import configurazione as configurazione_repo
from app.repositories import giocatori as giocatori_repo

NON_SINCRONIZZATA = "Non sincronizzata"
NON_SINCRONIZZATO = "Non sincronizzato"

# I campi di ogni giocatore, nell'ordine in cui viaggiano verso il browser.
# Servono sia alla riga della tabella sia alla scheda di dettaglio: viaggiano
# una volta sola e il JavaScript pesca da qui quelli che gli servono.
CAMPI = (
    "nome", "ruolo", "club", "squadra_att", "squadra_username",
    "detentore", "detentore_username", "tipo_contratto",
    "quotazione", "costo", "data_nascita", "scadenza_contratto_reale",
    "valore_mercato", "u21",
)


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
        "detentore": g["detentore_cartellino"],
        "detentore_username": g["detentore_username"],
        "tipo_contratto": g["tipo_contratto"],
        "quotazione": g["quot_att_mantra"],
        "costo": g["costo"],
        "data_nascita": formatta_data_nascita_con_eta(g["data_nascita"]) or NON_SINCRONIZZATA,
        "scadenza_contratto_reale": formatta_scadenza_contratto(g["scadenza_contratto"]) or NON_SINCRONIZZATA,
        "valore_mercato": formatta_valore_mercato_mln(g["valore_mercato"]) or NON_SINCRONIZZATO,
        "u21": stato_u21(g["data_nascita"], soglia_u21),
    }


def _tabella(giocatori: list[dict]) -> dict:
    """I giocatori senza ripetere i nomi dei campi a ogni riga."""
    return {
        "campi": list(CAMPI),
        "righe": [[g[campo] for campo in CAMPI] for g in giocatori],
    }


def _username_con_logo(giocatori: list[dict]) -> list[str]:
    """Le squadre di cui la pagina mostra il logo, fra righe e schede.

    Il blueprint ne ricava la versione dei file: i loghi non passano piu' da
    `url_for` in un template, quindi il `?v=` deve viaggiare con i dati.
    """
    return sorted({
        g[campo]
        for g in giocatori
        for campo in ("squadra_username", "detentore_username")
        if g[campo]
    })


def dati_pagina(cur) -> dict:
    soglia_u21 = configurazione_repo.soglia_u21(cur)
    giocatori = [_riga(g, soglia_u21) for g in giocatori_repo.listone(cur)]

    return {
        "totale_giocatori": len(giocatori),
        "dati_giocatori": _tabella(giocatori),
        "username_con_logo": _username_con_logo(giocatori),
        "ruoli_disponibili": ruoli_base_presenti([g["ruolo"] for g in giocatori]),
        "club_disponibili": sorted({g["club"] for g in giocatori if g["club"]}),
        "squadre_disponibili": sorted({g["squadra_att"] for g in giocatori if g["squadra_att"]}),
        "contratti_disponibili": sorted({g["tipo_contratto"] for g in giocatori if g["tipo_contratto"]}),
        "u21_threshold_year": soglia_u21,
    }
