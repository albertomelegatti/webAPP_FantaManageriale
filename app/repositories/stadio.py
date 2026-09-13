"""Stadi: livello e proprietario, uno per squadra."""


def elenco(cur) -> list[dict]:
    cur.execute("SELECT nome, proprietario, livello FROM stadio ORDER BY proprietario ASC;")
    return cur.fetchall()
