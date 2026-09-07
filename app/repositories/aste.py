"""Aste: impegni di crediti e slot occupati."""


def offerta_totale(cur, nome_squadra: str) -> int:
    """Somma delle offerte in aste ancora in corso: sono crediti gia' impegnati,
    che vanno sottratti da quelli spendibili."""
    cur.execute(
        """SELECT COALESCE(SUM(ultima_offerta), 0) AS totale FROM asta
           WHERE squadra_vincente = %s AND stato = 'in_corso';""",
        (nome_squadra,),
    )
    return cur.fetchone()["totale"]


def slot_impegnati(cur, nome_squadra: str) -> int:
    """Aste non ancora concluse a cui la squadra partecipa: ognuna potrebbe
    trasformarsi in un giocatore, quindi occupa uno slot in prospettiva."""
    cur.execute(
        """SELECT COUNT(id) AS n FROM asta
           WHERE %s = ANY(partecipanti) AND stato <> 'conclusa';""",
        (nome_squadra,),
    )
    return cur.fetchone()["n"]


def slot_occupati_totali(cur, nome_squadra: str) -> int:
    """Slot da giocatori sotto contratto piu' slot impegnati in aste, in
    un'unica query invece di due round-trip."""
    cur.execute(
        """
        SELECT
            (SELECT COUNT(id) FROM giocatore
                WHERE squadra_att = %s
                  AND tipo_contratto IN ('Hold', 'Indeterminato')) AS slot_giocatori,
            (SELECT COUNT(id) FROM asta
                WHERE %s = ANY(partecipanti) AND stato <> 'conclusa') AS slot_aste;
        """,
        (nome_squadra, nome_squadra),
    )
    riga = cur.fetchone()
    return riga["slot_giocatori"] + riga["slot_aste"]


def stato(cur, asta_id) -> str | None:
    cur.execute("SELECT stato FROM asta WHERE id = %s;", (asta_id,))
    riga = cur.fetchone()
    return riga["stato"] if riga else None


def e_iscritta(cur, asta_id, nome_squadra: str) -> bool:
    cur.execute("SELECT %s = ANY(partecipanti) AS iscritta FROM asta WHERE id = %s;",
                (nome_squadra, asta_id))
    riga = cur.fetchone()
    return bool(riga and riga["iscritta"])


def iscrivi(cur, asta_id, nome_squadra: str) -> None:
    cur.execute("UPDATE asta SET partecipanti = array_append(partecipanti, %s) WHERE id = %s;",
                (nome_squadra, asta_id))


def rinuncia(cur, asta_id, nome_squadra: str) -> None:
    cur.execute("UPDATE asta SET partecipanti = array_remove(partecipanti, %s) WHERE id = %s;",
                (nome_squadra, asta_id))


def visibili_alla_squadra(cur, nome_squadra: str) -> list[dict]:
    """Le aste che riguardano la squadra: quelle a cui partecipa, quelle ancora
    aperte alle iscrizioni, e quelle che ha vinto."""
    cur.execute(
        """SELECT a.id, g.nome, g.ruolo, g.club, a.squadra_vincente, a.ultima_offerta,
                  a.tempo_fine_asta, a.tempo_fine_mostra_interesse, a.stato, a.partecipanti
           FROM asta a JOIN giocatore g ON a.giocatore = g.id
           WHERE (a.stato = 'in_corso' AND %s = ANY(a.partecipanti))
              OR a.stato = 'mostra_interesse'
              OR (a.stato = 'conclusa' AND a.squadra_vincente = %s)
           ORDER BY a.tempo_fine_asta DESC;""",
        (nome_squadra, nome_squadra))
    return cur.fetchall()


def dettaglio(cur, asta_id) -> dict | None:
    cur.execute(
        """SELECT g.nome, g.ruolo, g.club, a.ultima_offerta, a.squadra_vincente,
                  a.tempo_fine_asta, a.partecipanti
           FROM asta a JOIN giocatore g ON a.giocatore = g.id
           WHERE a.id = %s;""", (asta_id,))
    return cur.fetchone()


def dati_per_rilancio(cur, asta_id) -> dict | None:
    """Blocca la riga per aggiornamenti concorrenti prima di leggerla: due
    rilanci simultanei devono essere serializzati, non sovrascriversi."""
    cur.execute(
        "SELECT ultima_offerta, squadra_vincente, stato FROM asta WHERE id = %s FOR UPDATE;",
        (asta_id,))
    return cur.fetchone()


def registra_rilancio(cur, asta_id, offerta: int, nome_squadra: str) -> None:
    """Ogni rilancio fa ripartire il conto alla rovescia di un giorno."""
    cur.execute(
        """UPDATE asta SET ultima_offerta = %s, squadra_vincente = %s,
                           tempo_fine_asta = (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day'
           WHERE id = %s;""", (offerta, nome_squadra, asta_id))


def giocatore_dell_asta(cur, asta_id) -> int | None:
    cur.execute("SELECT giocatore FROM asta WHERE id = %s;", (asta_id,))
    riga = cur.fetchone()
    return riga["giocatore"] if riga else None
