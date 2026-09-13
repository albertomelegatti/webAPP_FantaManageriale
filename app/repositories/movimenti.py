"""Movimenti di mercato: il registro pubblico di cosa e' successo."""

# Le aste hanno una loro pagina: nel registro dei movimenti sarebbero rumore.
ESCLUDI_ASTE = "evento NOT ILIKE %(asta)s"
MARCATORE_ASTA = "%🏷️ ASTA%"


def per_squadra(cur, nome_squadra: str) -> list[dict]:
    """I movimenti che coinvolgono la squadra, dalla colonna `squadre`.

    Prima era una ricerca per sottostringa sul testo dell'evento: funzionava
    solo perche' nessuna squadra ha un nome sottostringa di un'altra, e non era
    indicizzabile. La colonna e' popolata esplicitamente da chi scrive il
    movimento (vedi telegram_utils.salva_movimento), non dedotta dal testo.
    """
    cur.execute(
        f"""SELECT data, evento, stagione FROM movimenti_squadra
            WHERE squadre @> ARRAY[%(squadra)s]::text[] AND {ESCLUDI_ASTE}
            ORDER BY data DESC;""",
        {"squadra": nome_squadra, "asta": MARCATORE_ASTA})
    return cur.fetchall()


def tutti(cur) -> list[dict]:
    cur.execute(
        f"""SELECT data, evento, stagione FROM movimenti_squadra
            WHERE {ESCLUDI_ASTE} ORDER BY data DESC;""",
        {"asta": MARCATORE_ASTA})
    return cur.fetchall()


def salva(cur, evento: str, squadre: list[str], stagione: str) -> None:
    """Registra un movimento, con le squadre coinvolte dichiarate esplicitamente
    da chi lo scrive: mai piu' di due, secondo i casi visti finora (un'azione di
    una squadra, o uno scambio fra due)."""
    cur.execute(
        "INSERT INTO movimenti_squadra (evento, data, squadre, stagione) VALUES (%s, NOW(), %s, %s);",
        (evento, squadre, stagione))
