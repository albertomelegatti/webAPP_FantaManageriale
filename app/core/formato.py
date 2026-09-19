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


# Cartella di stagione nell'URL dei campioncini: non è un anno, è cambiata
# raramente rispetto alle stagioni osservate (vedi CronJob/fantacalcio_card_schema.sql).
# Se in futuro fantacalcio.it la aggiorna le immagini vecchie smettono di
# caricare tutte insieme: primo segnale per aggiornare questa costante.
_CAMPIONCINO_STAGIONE = "21"


def url_campioncino(id_fantacalcio):
    """URL del campioncino (la card ufficiale) di un giocatore su
    fantacalcio.it, None se non ancora abbinato (vedi
    app/services/fantacalcio.py)."""
    if id_fantacalcio is None:
        return None
    return f"https://content.fantacalcio.it/web/campioncini/{_CAMPIONCINO_STAGIONE}/card/{id_fantacalcio}.png"
