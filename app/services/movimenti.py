"""
Composizione della pagina dei movimenti di mercato.

Il registro conta centinaia di righe, ognuna con il testo integrale del
movimento, e il server le mandava tutte gia' impaginate in HTML: mezzo megabyte
che il browser doveva costruire per intero, per poi nasconderne la maggior parte
al primo filtro.

Come per il listone, qui viaggiano solo i dati, in forma compatta - i nomi dei
campi dichiarati una volta, poi una riga di valori per movimento - e le righe le
disegna il browser una pagina alla volta (static/js/movimenti_mercato.js).
"""

from app.repositories import movimenti as movimenti_repo
from app.repositories import squadre as squadre_repo

# I campi di ogni movimento, nell'ordine in cui viaggiano verso il browser.
CAMPI = ("data", "evento", "stagione")


def _valori(m: dict) -> list:
    # `str` e non `isoformat`: e' la stessa conversione che faceva Jinja
    # stampando {{ m.data }}, quindi la data appare esattamente come prima.
    return [str(m["data"]), m["evento"], m["stagione"]]


def _stagioni(movimenti: list[dict]) -> list[str]:
    """Le stagioni presenti, dalla piu' recente.

    L'ordine e' quello alfabetico invertito, che sul formato usato ('24-25',
    '25-26') coincide con quello cronologico.
    """
    return sorted({m["stagione"] for m in movimenti if m["stagione"]}, reverse=True)


def dati_pagina(cur) -> dict:
    movimenti = movimenti_repo.tutti(cur)

    return {
        "dati_movimenti": {
            "campi": list(CAMPI),
            "righe": [_valori(m) for m in movimenti],
        },
        "stagioni_disponibili": _stagioni(movimenti),
        "squadre": squadre_repo.nomi(cur),
    }
