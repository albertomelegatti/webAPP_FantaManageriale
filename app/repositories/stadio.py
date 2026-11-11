"""Stadi: livello e proprietario, uno per squadra."""


def elenco(cur) -> list[dict]:
    cur.execute("SELECT nome, proprietario, livello FROM stadio ORDER BY proprietario ASC;")
    return cur.fetchall()


def imposta(cur, proprietario: str, nome: str, livello: int) -> None:
    """Nome e livello dello stadio della squadra; lo crea se la squadra non ne ha.

    Una squadra ha al massimo uno stadio (proprietario e' unique), quindi si
    aggiorna per proprietario. Solleva UniqueViolation se il nome e' gia' di
    un altro stadio (e' la chiave primaria).
    """
    cur.execute("UPDATE stadio SET nome = %s, livello = %s WHERE proprietario = %s;",
                (nome, livello, proprietario))
    if cur.rowcount == 0:
        cur.execute("INSERT INTO stadio (nome, livello, proprietario) VALUES (%s, %s, %s);",
                    (nome, livello, proprietario))


def rendite(cur) -> list[int] | None:
    """Rendita annuale per livello (l'indice della lista e' il livello).

    None se la tabella stadio_livello non c'e' ancora (script in CronJob/ non
    ancora lanciato) o e' vuota: il chiamante ripiega sui valori di default.
    """
    cur.execute("SELECT to_regclass('stadio_livello') IS NOT NULL AS esiste;")
    if not cur.fetchone()["esiste"]:
        return None
    cur.execute("SELECT rendita FROM stadio_livello ORDER BY livello;")
    return [r["rendita"] for r in cur.fetchall()] or None


def imposta_rendita(cur, livello: int, rendita: int) -> None:
    cur.execute("UPDATE stadio_livello SET rendita = %s WHERE livello = %s;", (rendita, livello))
