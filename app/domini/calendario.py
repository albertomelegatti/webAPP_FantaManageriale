"""
Calendario della stagione: anni ammessi per la scadenza dei prestiti.

Funzione pura, con la data di riferimento iniettabile per poterla testare senza
dipendere da quando gira il test.

Vive qui e non dentro un blueprint perché serve sia ai prestiti sia al mercato:
prima era una funzione privata di user_prestiti che user_mercato importava
attraversando il trattino basso.
"""

from datetime import datetime

# Un prestito scade il 1 luglio. Chi lo propone dopo quella data sta guardando
# alla stagione successiva, quindi l'anno minimo proponibile avanza di uno.
GIORNO_SCADENZA = (7, 1)


def anni_prestito_ammessi(riferimento: datetime | None = None) -> tuple[list[int], int]:
    """Anni proponibili come scadenza di un prestito, e quello predefinito.

    Restituisce ([anno, anno+1], anno).
    """
    riferimento = riferimento or datetime.now()
    mese, giorno = GIORNO_SCADENZA
    limite = datetime(riferimento.year, mese, giorno, 23, 59, 59)
    primo_anno = riferimento.year if riferimento <= limite else riferimento.year + 1
    return [primo_anno, primo_anno + 1], primo_anno
