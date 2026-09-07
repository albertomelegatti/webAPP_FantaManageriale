"""Giocatori: anagrafica e conteggi di rosa."""

# Contratti che occupano uno slot in rosa. Prestiti e primavera non contano.
CONTRATTI_CHE_OCCUPANO_SLOT = ('Hold', 'Indeterminato')


def nome(cur, id_giocatore: int) -> str:
    cur.execute("SELECT nome FROM giocatore WHERE id = %s;", (id_giocatore,))
    return cur.fetchone()["nome"]


def quotazione(cur, id_giocatore: int) -> int:
    cur.execute("SELECT quot_att_mantra FROM giocatore WHERE id = %s;", (id_giocatore,))
    return int(cur.fetchone()["quot_att_mantra"])


def slot_occupati_da_giocatori(cur, nome_squadra: str) -> int:
    cur.execute(
        """SELECT COUNT(id) AS n FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto IN ('Hold', 'Indeterminato');""",
        (nome_squadra,),
    )
    return cur.fetchone()["n"]


def slot_prestiti_in(cur, nome_squadra: str) -> int:
    cur.execute(
        """SELECT COUNT(id) AS n FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto = 'Fanta-Prestito';""",
        (nome_squadra,),
    )
    return cur.fetchone()["n"]


def nomi_per_id(cur, id_giocatori) -> dict[int, str]:
    """{id: nome} per un elenco di id, in una sola query.

    Risolve i nomi dei giocatori citati negli scambi senza interrogare il
    database una volta per scambio.
    """
    id_giocatori = [int(g) for g in (id_giocatori or []) if g]
    if not id_giocatori:
        return {}
    cur.execute("SELECT id, nome FROM giocatore WHERE id = ANY(%s);", (id_giocatori,))
    return {r["id"]: r["nome"] for r in cur.fetchall()}
