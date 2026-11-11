"""Accrediti annuali: stagione corrente, chiavi del registro e somma dei premi.

Calcoli puri, senza database: si provano senza connessione. Il registro che
impedisce di accreditare due volte (tabella accrediti_annuali) usa le chiavi
costruite qui.
"""

from datetime import date

COMPETIZIONI = ("Campionato", "Coppa")


def stagione_corrente(oggi: date) -> str:
    """La stagione in corso, nel formato dell'albo d'oro ("26-27").

    Va dal 2 luglio di un anno al 2 luglio dell'anno dopo, come
    telegram_utils.get_stagione(): prima del 2 luglio e' ancora quella
    iniziata l'anno precedente.
    """
    inizio = oggi.year - 1 if (oggi.month, oggi.day) < (7, 2) else oggi.year
    return f"{inizio % 100:02d}-{(inizio + 1) % 100:02d}"


def chiave_albo_oro(stagione: str, competizione: str) -> str:
    return f"albo_oro:{stagione}:{competizione}"


def chiave_rendite_stadi(stagione: str) -> str:
    return f"rendite_stadi:{stagione}"


def crediti_per_squadra(righe: list[dict], competizione: str) -> list[tuple[str, int]]:
    """[(squadra, crediti)] dei premi di una competizione, per i piazzamenti di una stagione.

    Una squadra puo' comparire in piu' righe della stessa competizione (la Coppa
    ha gironi e finali): i suoi crediti si sommano. Chi totalizza 0 non riceve
    niente e non compare. Ordinato dal premio piu' alto, a parita' per nome.
    """
    totali: dict[str, int] = {}
    for r in righe:
        if r["competizione"] == competizione and r["squadra"]:
            totali[r["squadra"]] = totali.get(r["squadra"], 0) + (r["crediti_generati"] or 0)
    return sorted(((s, c) for s, c in totali.items() if c > 0), key=lambda x: (-x[1], x[0]))
