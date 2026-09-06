"""Configurazione globale: date di chiusura e soglia U21.

Una riga sola nella tabella general_config, che cambia forse due volte a
stagione ma viene letta a ogni richiesta di mercato, aste e prestiti.
"""

from app.core.tempo import oggi


def leggi(cur) -> dict | None:
    cur.execute(
        "SELECT mercato_chiusura, aste_chiusura, u21_threshold_year"
        " FROM general_config WHERE id = 1;"
    )
    return cur.fetchone()


def _aperto(chiusura) -> bool:
    """Nessuna data impostata significa sempre aperto. Altrimenti la sezione
    chiude a partire dalla mezzanotte del giorno indicato."""
    return chiusura is None or oggi() < chiusura


def mercato_aperto(cur) -> bool:
    config = leggi(cur)
    return _aperto(config["mercato_chiusura"] if config else None)


def aste_aperte(cur) -> bool:
    config = leggi(cur)
    return _aperto(config["aste_chiusura"] if config else None)


def stato_gate(cur) -> dict:
    """Stato completo di mercato e aste in un'unica lettura: le pagine di menu
    mostrano le voci disabilitate con la data di chiusura nel tooltip, quindi
    servono insieme sia le date sia i due booleani."""
    config = leggi(cur)
    mercato_chiusura = config["mercato_chiusura"] if config else None
    aste_chiusura = config["aste_chiusura"] if config else None

    return {
        "mercato_chiusura": mercato_chiusura,
        "mercato_aperto": _aperto(mercato_chiusura),
        "aste_chiusura": aste_chiusura,
        "aste_aperte": _aperto(aste_chiusura),
        "u21_threshold_year": config["u21_threshold_year"] if config else None,
    }


def soglia_u21(cur) -> int | None:
    """Anno di nascita da cui un giocatore e' considerato U21.

    Gli U21 sono acquistabili solo tramite draft, non in asta. Nessuna soglia
    impostata significa nessun filtro.
    """
    config = leggi(cur)
    return config["u21_threshold_year"] if config else None
