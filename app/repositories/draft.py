"""Pick del draft."""


def _anno(valore) -> str:
    """Il campo anno e' una data sul database ma viene mostrato come solo anno."""
    if valore is None:
        return "N/D"
    return str(valore.year if hasattr(valore, "year") else valore)


def descrizioni_per_id(cur, pick_ids) -> dict[int, str]:
    """{id: '2027 - Giro: 1°'} per un elenco di pick, in una sola query.

    Prima ogni riga di scambio interrogava il draft due volte, una per le pick
    offerte e una per quelle richieste.
    """
    pick_ids = [int(p) for p in (pick_ids or []) if p]
    if not pick_ids:
        return {}

    cur.execute(
        """SELECT id, anno, giro, numero FROM draft
           WHERE id = ANY(%s) ORDER BY anno, giro, numero;""",
        (pick_ids,),
    )
    return {r["id"]: f"{_anno(r['anno'])} - Giro: {r['giro']}°" for r in cur.fetchall()}


def esistono_tutte(cur, pick_ids) -> bool:
    """Verifica che ogni id corrisponda a una pick reale, prima di accettarla
    in una proposta di scambio."""
    pick_ids = [int(p) for p in (pick_ids or []) if p]
    if not pick_ids:
        return True
    cur.execute("SELECT COUNT(*) AS n FROM draft WHERE id = ANY(%s);", (pick_ids,))
    return cur.fetchone()["n"] == len(set(pick_ids))


def pick_della_squadra(cur, nome_squadra: str) -> list[dict]:
    cur.execute(
        """SELECT d.detentore_originale, d.anno, d.numero, g.nome AS giocatore_scelto
           FROM draft d LEFT JOIN giocatore g ON d.id_giocatore_scelto = g.id
           WHERE d.detentore_att = %s
           ORDER BY d.anno, d.numero;""",
        (nome_squadra,))
    return cur.fetchall()
