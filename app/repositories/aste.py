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
