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


def per_id(cur, id_prestito) -> dict | None:
    cur.execute("SELECT * FROM prestito WHERE id = %s;", (id_prestito,))
    return cur.fetchone()


def in_attesa_per_squadra(cur, nome_squadra: str) -> list[dict]:
    """Richieste di prestito ancora da decidere, escluse quelle legate a uno
    scambio: quelle si accettano dalla pagina del mercato, non da qui."""
    cur.execute(
        """SELECT *, p.id AS prestito_id, p.note, p.costo_prestito,
                  p.tipo_prestito, p.crediti_riscatto
           FROM prestito p JOIN giocatore g ON p.giocatore = g.id
           WHERE (p.squadra_prestante = %s OR p.squadra_ricevente = %s)
             AND p.stato = 'in_attesa'
             AND NOT EXISTS (SELECT 1 FROM scambio s WHERE p.id = ANY(s.prestito_associato));""",
        (nome_squadra, nome_squadra))
    return cur.fetchall()


def cambia_stato(cur, id_prestito, nuovo_stato: str) -> None:
    cur.execute("UPDATE prestito SET stato = %s WHERE id = %s;", (nuovo_stato, id_prestito))


def rifiuta_concorrenti(cur, squadra_prestante: str, id_giocatore) -> None:
    """Accettato un prestito, le altre richieste in attesa per lo stesso
    giocatore dalla stessa squadra prestante decadono."""
    cur.execute(
        """UPDATE prestito SET stato = 'rifiutato'
           WHERE squadra_prestante = %s AND giocatore = %s AND stato = 'in_attesa';""",
        (squadra_prestante, id_giocatore))


def crea(cur, giocatore, squadra_prestante, squadra_ricevente, data_fine,
         note, costo_prestito, tipo_prestito, crediti_riscatto) -> int:
    cur.execute(
        """INSERT INTO prestito (giocatore, squadra_prestante, squadra_ricevente, stato,
                                 data_inizio, data_fine, note, costo_prestito,
                                 tipo_prestito, crediti_riscatto)
           VALUES (%s, %s, %s, 'in_attesa', NOW() AT TIME ZONE 'Europe/Rome',
                   %s, %s, %s, %s, %s)
           RETURNING id;""",
        (giocatore, squadra_prestante, squadra_ricevente, data_fine, note,
         costo_prestito, tipo_prestito, crediti_riscatto))
    return cur.fetchone()["id"]
