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


# Cartella nell'URL dei campioncini: non e' una stagione, e' un'edizione
# grafica. La 20 e' l'illustrazione a caricatura "classica" (un personaggio
# disegnato a mano, es. Thuram) - le altre edizioni (es. la 21) coprono anche
# chi manca da questa (circa un terzo, soprattutto trasferimenti recenti non
# ancora illustrati a mano) ma con stili incoerenti fra loro, da una card
# statistica stile FUT a una sagoma anonima. Deliberatamente non c'e' un
# fallback su quelle altre edizioni: se manca la caricatura non si mostra
# nessuna foto (ogni <img> che la usa nasconde se' stessa via onerror, vedi
# es. app/templates/_macros.html) invece di un'immagine fuori stile.
_CAMPIONCINO_STAGIONE = "20"


def url_campioncino(id_fantacalcio):
    """URL del campioncino (la card ufficiale) di un giocatore su
    fantacalcio.it, None se non ancora abbinato (vedi
    app/services/fantacalcio.py)."""
    if id_fantacalcio is None:
        return None
    return f"https://content.fantacalcio.it/web/campioncini/{_CAMPIONCINO_STAGIONE}/card/{id_fantacalcio}.png"
