"""Vetrina: giocatori messi a disposizione dalle squadre."""


def decadi(cur, giocatore_ids) -> None:
    """Rimuove dalla vetrina i giocatori indicati, se presenti.

    Un giocatore che cambia proprietario o situazione contrattuale - svincolo,
    prestito, riscatto, scambio - non e' piu' quello che la squadra aveva messo
    in vetrina, quindi l'annuncio decade.
    """
    if not isinstance(giocatore_ids, (list, tuple, set)):
        giocatore_ids = [giocatore_ids]
    giocatore_ids = [int(g) for g in giocatore_ids if g]
    if not giocatore_ids:
        return

    cur.execute("DELETE FROM vetrina WHERE id_giocatore = ANY(%s);", (giocatore_ids,))
