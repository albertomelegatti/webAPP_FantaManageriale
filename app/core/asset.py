"""
Versione dei file statici, da usare come `?v=` per invalidare la cache del browser.

Stava dentro l'application factory, come helper privato del solo ambiente Jinja.
Da quando il listone disegna le righe nel browser, i suoi loghi non passano piu'
da `url_for` in un template: la versione va calcolata nel blueprint e spedita
insieme ai dati, quindi la funzione deve essere importabile da fuori.
"""

import os
import time

# Secondi di validita' del valore in cache: senza, una pagina con molte righe
# farebbe uno stat() del filesystem per ogni riga a ogni caricamento.
TTL = 5

_cache = {}


def versione(cartella_statici: str, percorso_relativo: str) -> int:
    """Timestamp di modifica di un file statico, 0 se il file non e' leggibile."""
    adesso = time.monotonic()
    in_cache = _cache.get(percorso_relativo)
    if in_cache and adesso - in_cache[1] < TTL:
        return in_cache[0]

    try:
        valore = int(os.path.getmtime(os.path.join(cartella_statici, percorso_relativo)))
    except OSError:
        valore = 0

    _cache[percorso_relativo] = (valore, adesso)
    return valore
