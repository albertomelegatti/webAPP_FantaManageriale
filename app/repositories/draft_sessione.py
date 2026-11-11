"""Stato del draft di un anno: preparato -> aperto -> chiuso.

Una riga per anno. `anno` e' un intero (anno del draft), mentre `draft.anno` e'
una data al 1 gennaio: il collegamento sta nei repository, non nel database.
Al massimo un draft puo' essere aperto alla volta (indice unico parziale).

Ogni transizione e' un UPDATE con la condizione sullo stato di partenza, cosi'
due click ravvicinati non passano entrambi: il secondo trova 0 righe e il
chiamante lo vede dal valore restituito.
"""


def leggi(cur, anno: int) -> dict | None:
    cur.execute("SELECT * FROM draft_sessione WHERE anno = %s;", (anno,))
    return cur.fetchone()


def aperto(cur) -> dict | None:
    """Il draft attualmente aperto, se c'e'."""
    cur.execute("SELECT * FROM draft_sessione WHERE stato = 'aperto';")
    return cur.fetchone()


def prepara(cur, anno: int) -> bool:
    """Crea la sessione o ne aggiorna la data di generazione dell'ordine.

    Solo finche' e' `preparato`: a draft aperto o chiuso l'ordine non si
    rigenera. Ritorna False se non e' stato possibile.
    """
    cur.execute(
        """INSERT INTO draft_sessione (anno, stato, ordine_generato_il)
           VALUES (%s, 'preparato', now())
           ON CONFLICT (anno) DO UPDATE SET ordine_generato_il = now()
           WHERE draft_sessione.stato = 'preparato'
           RETURNING anno;""",
        (anno,))
    return cur.fetchone() is not None


def apri(cur, anno: int) -> bool:
    """preparato -> aperto. False se non era preparato.

    Se un altro draft e' gia' aperto l'indice unico fa fallire la query:
    l'errore sale al chiamante, che nel suo `try` annulla la transazione.
    """
    cur.execute(
        """UPDATE draft_sessione SET stato = 'aperto', aperto_il = now()
           WHERE anno = %s AND stato = 'preparato' RETURNING anno;""",
        (anno,))
    return cur.fetchone() is not None


def chiudi(cur, anno: int) -> bool:
    """aperto -> chiuso. False se non era aperto."""
    cur.execute(
        """UPDATE draft_sessione SET stato = 'chiuso', chiuso_il = now()
           WHERE anno = %s AND stato = 'aperto' RETURNING anno;""",
        (anno,))
    return cur.fetchone() is not None
