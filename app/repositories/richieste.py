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
