"""Movimenti di mercato: il registro pubblico di cosa e' successo."""

# Le aste hanno una loro pagina: nel registro dei movimenti sarebbero rumore.
ESCLUDI_ASTE = "evento NOT ILIKE %(asta)s"
MARCATORE_ASTA = "%🏷️ ASTA%"


def per_squadra(cur, nome_squadra: str) -> list[dict]:
    """I movimenti che citano la squadra.

    Il filtro e' una ricerca per sottostringa sul testo dell'evento, perche' il
    legame con la squadra non e' registrato in una colonna: e' l'unico modo
    disponibile oggi. Ha due conseguenze note - non e' indicizzabile, e due
    squadre con un nome uno sottostringa dell'altro si mescolerebbero - che si
    risolvono solo aggiungendo una colonna esplicita.
    """
    cur.execute(
        f"""SELECT data, evento, stagione FROM movimenti_squadra
            WHERE evento ILIKE %(squadra)s AND {ESCLUDI_ASTE}
            ORDER BY data DESC;""",
        {"squadra": f"%{nome_squadra}%", "asta": MARCATORE_ASTA})
    return cur.fetchall()


def tutti(cur) -> list[dict]:
    cur.execute(
        f"""SELECT data, evento, stagione FROM movimenti_squadra
            WHERE {ESCLUDI_ASTE} ORDER BY data DESC;""",
        {"asta": MARCATORE_ASTA})
    return cur.fetchall()
