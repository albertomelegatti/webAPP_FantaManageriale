"""Registro degli accrediti annuali (tabella accrediti_annuali).

Una riga per accredito gia' eseguito, con chiave primaria. La scrittura di
`registra` e' la guardia contro il doppio accredito: vedi il servizio.
Lo schema sta in CronJob/accrediti_annuali_schema.sql.
"""


def disponibile(cur) -> bool:
    """La tabella esiste? Senza, non si accredita niente (nessuna guardia)."""
    cur.execute("SELECT to_regclass('public.accrediti_annuali') IS NOT NULL AS ok;")
    return cur.fetchone()["ok"]


def leggi(cur, chiave: str) -> dict | None:
    cur.execute("SELECT * FROM accrediti_annuali WHERE chiave = %s;", (chiave,))
    return cur.fetchone()


def registra(cur, chiave: str, tipo: str, stagione: str, competizione: str | None,
             da: str, squadre: int, totale: int) -> bool:
    """Segna l'accredito come eseguito. False se la chiave esiste gia'.

    E' l'unica porta d'ingresso: ON CONFLICT lascia passare una sola richiesta.
    Con due richieste simultanee la seconda aspetta il commit della prima e poi
    trova la riga, quindi non accredita.
    """
    cur.execute(
        """INSERT INTO accrediti_annuali (chiave, tipo, stagione, competizione, eseguito_da, squadre, totale)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (chiave) DO NOTHING
           RETURNING chiave;""",
        (chiave, tipo, stagione, competizione, da, squadre, totale))
    return cur.fetchone() is not None
