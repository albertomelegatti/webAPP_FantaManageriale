"""Vetrina: giocatori messi a disposizione dalle squadre."""


def elenco(cur) -> list[dict]:
    """I giocatori attualmente in vetrina, dalle sole squadre in gioco.

    Un giocatore posseduto da 'Svincolato' non e' mai in vetrina per
    definizione (nessuno lo mette in vendita), ma il filtro sulla squadra
    detentrice e' quello che la query ha sempre applicato: lo si mantiene.
    """
    cur.execute("""
        SELECT g.nome, g.ruolo, g.id_fantacalcio, g.detentore_cartellino, g.quot_att_mantra, v.stato, v.note, v.data_inserimento
        FROM giocatore g
        JOIN vetrina v ON g.id = v.id_giocatore
        WHERE g.squadra_att <> 'Svincolato' AND g.detentore_cartellino <> 'Svincolato'
        ORDER BY g.nome;
    """)
    return cur.fetchall()


def esiste(cur, id_giocatore) -> bool:
    cur.execute("SELECT 1 FROM vetrina WHERE id_giocatore = %s;", (id_giocatore,))
    return cur.fetchone() is not None


def rimuovi(cur, id_giocatore) -> None:
    cur.execute("DELETE FROM vetrina WHERE id_giocatore = %s;", (id_giocatore,))


def aggiorna(cur, id_giocatore, stato: str, note: str | None) -> None:
    cur.execute(
        "UPDATE vetrina SET stato = %s, note = %s WHERE id_giocatore = %s;",
        (stato, note, id_giocatore))


def crea(cur, id_giocatore, stato: str, note: str | None) -> None:
    cur.execute(
        """INSERT INTO vetrina (id_giocatore, stato, note, data_inserimento)
           VALUES (%s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome');""",
        (id_giocatore, stato, note))


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
