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
# grafica. La 20 era l'illustrazione a caricatura "classica" (un personaggio
# disegnato a mano, es. Thuram), ma e' un'edizione ormai superata lato
# fantacalcio.it: oltre a mancare per una parte dei giocatori, per alcuni id
# risponde 200 con un'immagine sbagliata invece di un errore (visto con
# Cissè, id 6618: la 20 mostra un personaggio anonimo che non e' lui). La 21
# e' quella che fantacalcio.it stesso usa oggi su ogni pagina profilo, per
# ogni giocatore (verificato sulla pagina di Dybala, che pure ha la 20): e'
# sempre in stile caricatura, personalizzata o un placeholder col colore del
# club reale, ed e' l'unica fonte affidabile.
_CAMPIONCINO_STAGIONE = "21"


def url_campioncino(id_fantacalcio):
    """URL del campioncino (la card ufficiale) di un giocatore su
    fantacalcio.it, None se non ancora abbinato o se non c'e' (valore
    negativo, vedi NESSUNA_CORRISPONDENZA in app/domini/matching_fantacalcio.py
    e app/services/fantacalcio.py)."""
    if id_fantacalcio is None or id_fantacalcio <= 0:
        return None
    return f"https://content.fantacalcio.it/web/campioncini/{_CAMPIONCINO_STAGIONE}/card/{id_fantacalcio}.png"
