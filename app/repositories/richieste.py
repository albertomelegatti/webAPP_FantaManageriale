"""Richieste di modifica contratto."""


def id_con_richiesta_in_elaborazione(cur, id_giocatori) -> set[int]:
    """Sottoinsieme degli id che hanno gia' una richiesta aperta, in una query.

    Prima questa informazione veniva chiesta un giocatore alla volta dentro il
    ciclo che costruisce la pagina: su una rosa da trenta giocatori erano trenta
    interrogazioni per un dato che sta in una sola.
    """
    id_giocatori = [int(g) for g in (id_giocatori or []) if g]
    if not id_giocatori:
        return set()

    cur.execute(
        """SELECT DISTINCT giocatore FROM richiesta_modifica_contratto
           WHERE giocatore = ANY(%s) AND stato = 'in_elaborazione';""",
        (id_giocatori,),
    )
    return {r["giocatore"] for r in cur.fetchall()}


def rifiuta(cur, id_richiesta) -> None:
    cur.execute("UPDATE richiesta_modifica_contratto SET stato = 'rifiutata' WHERE id = %s;", (id_richiesta,))


def accetta(cur, id_richiesta) -> None:
    cur.execute("UPDATE richiesta_modifica_contratto SET stato = 'accettata' WHERE id = %s;", (id_richiesta,))


def dettaglio(cur, id_richiesta) -> dict | None:
    cur.execute(
        """SELECT giocatore, contratto_richiesto, crediti_richiesti, squadra_richiedente
           FROM richiesta_modifica_contratto WHERE id = %s;""",
        (id_richiesta,))
    return cur.fetchone()


def elenco(cur) -> list[dict]:
    """Tutte le richieste, dalla piu' recente, con i dati del giocatore per la
    pagina di amministrazione."""
    cur.execute(
        """SELECT r.id, g.nome, g.tipo_contratto, g.ruolo, g.club, r.giocatore,
                  r.contratto_richiesto, r.squadra_richiedente, r.crediti_richiesti,
                  r.messaggio, r.data, r.stato
           FROM richiesta_modifica_contratto AS r
           JOIN giocatore AS g ON r.giocatore = g.id
           ORDER BY data DESC;""")
    return cur.fetchall()


def crea(cur, id_giocatore, contratto_richiesto, squadra_richiedente,
         crediti_richiesti, messaggio) -> int:
    cur.execute(
        """INSERT INTO richiesta_modifica_contratto
               (giocatore, contratto_richiesto, squadra_richiedente,
                crediti_richiesti, messaggio, data, stato)
           VALUES (%s, %s, %s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome', 'in_elaborazione')
           RETURNING id;""",
        (id_giocatore, contratto_richiesto, squadra_richiedente, crediti_richiesti, messaggio),
    )
    return cur.fetchone()["id"]
