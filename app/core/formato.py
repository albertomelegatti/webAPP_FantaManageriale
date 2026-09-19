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


# Cartelle nell'URL dei campioncini: non sono stagioni, sono edizioni grafiche
# diverse. La 20 e' l'illustrazione a caricatura "classica" (un personaggio
# disegnato a mano, es. Thuram); la 21 copre tutti i giocatori (la 20 ne manca
# circa un terzo, soprattutto trasferimenti recenti non ancora illustrati a
# mano) ma per chi manca dalla 20 mostra una card statistica generata al volo,
# visivamente diversa dalla caricatura (es. Malen). La 20 e' quindi la fonte
# preferita per uno stile coerente; ogni <img> che la usa ha un onerror lato
# client che ripiega sulla 21 se la 20 non esiste per quel giocatore, invece
# di lasciare un'immagine rotta (vedi es. app/templates/_macros.html).
_CAMPIONCINO_STAGIONE = "20"


def url_campioncino(id_fantacalcio):
    """URL del campioncino (la card ufficiale) di un giocatore su
    fantacalcio.it, None se non ancora abbinato (vedi
    app/services/fantacalcio.py)."""
    if id_fantacalcio is None:
        return None
    return f"https://content.fantacalcio.it/web/campioncini/{_CAMPIONCINO_STAGIONE}/card/{id_fantacalcio}.png"
