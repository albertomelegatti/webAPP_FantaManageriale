"""
Formattazione di valori per l'interfaccia. Funzioni pure.

Le date stanno in app/core/tempo.py; qui i numeri.
"""


def formatta_valore_mercato_mln(valore_euro):
    """Valore di mercato in euro -> stringa in milioni: 750000 -> '0,75 Mln',
    1500000 -> '1,5 Mln', 75000000 -> '75 Mln'.

    Sempre in milioni, virgola come separatore decimale, zeri finali tolti.
    None se il valore non c'e' (non ancora sincronizzato da Transfermarkt).
    """
    if valore_euro is None:
        return None
    milioni = valore_euro / 1_000_000
    testo = f"{milioni:.2f}".rstrip("0").rstrip(".") or "0"
    return f"{testo.replace('.', ',')} Mln"
