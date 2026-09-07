"""Prestiti."""

# Forma abbreviata mostrata nel riepilogo di uno scambio.
TIPO_ABBREVIATO = {
    'secco': 'Secco',
    'diritto_di_riscatto': 'DDR',
    'obbligo_di_riscatto': 'ODR',
}


def descrizioni_per_id(cur, prestito_ids) -> dict[int, dict]:
    """{id: {'testo': '• Rossi [Prestito DDR (risc. 20)]', 'squadra_prestante': ...}}

    Il testo e' gia' composto qui perche' richiede il nome del giocatore, che
    arriva dalla stessa JOIN: comporlo altrove costringerebbe a una seconda
    query o a far girare la riga grezza fino al template.
    """
    prestito_ids = [int(p) for p in (prestito_ids or []) if p]
    if not prestito_ids:
        return {}

    cur.execute(
        """SELECT p.id, g.nome, p.tipo_prestito, p.crediti_riscatto, p.squadra_prestante
           FROM prestito p JOIN giocatore g ON p.giocatore = g.id
           WHERE p.id = ANY(%s);""",
        (prestito_ids,),
    )

    descrizioni = {}
    for riga in cur.fetchall():
        tipo = TIPO_ABBREVIATO.get(riga["tipo_prestito"], riga["tipo_prestito"])
        riscatto = riga["crediti_riscatto"]
        suffisso = f" (risc. {riscatto})" if riscatto and riscatto > 0 else ""
        descrizioni[riga["id"]] = {
            "testo": f"• {riga['nome']} [Prestito {tipo}{suffisso}]",
            "squadra_prestante": riga["squadra_prestante"],
        }
    return descrizioni
