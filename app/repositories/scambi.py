"""Scambi: proposte di mercato fra due squadre."""


def per_squadra(cur, nome_squadra: str) -> list[dict]:
    """Tutte le proposte che coinvolgono la squadra, come proponente o come
    destinataria, dalla piu' recente."""
    cur.execute(
        """SELECT * FROM scambio
           WHERE squadra_proponente = %s OR squadra_destinataria = %s
           ORDER BY data_proposta DESC;""",
        (nome_squadra, nome_squadra),
    )
    return cur.fetchall()


def per_id(cur, id_scambio) -> dict | None:
    cur.execute("SELECT * FROM scambio WHERE id = %s;", (id_scambio,))
    return cur.fetchone()
