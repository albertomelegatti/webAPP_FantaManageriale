"""Formazione (campetto): modulo scelto e giocatori assegnati a ogni slot."""

from psycopg2.extras import Json


def leggi(cur, nome_squadra: str) -> dict | None:
    """Modulo e slot salvati per la squadra, None se non ha mai salvato nulla."""
    cur.execute(
        """SELECT modulo, slot FROM formazione WHERE squadra = %s;""",
        (nome_squadra,))
    return cur.fetchone()


def salva(cur, nome_squadra: str, modulo: str, slot: list[dict]) -> None:
    """Sovrascrive modulo e slot della squadra (crea la riga se non esiste)."""
    cur.execute(
        """INSERT INTO formazione (squadra, modulo, slot, aggiornata_il)
           VALUES (%s, %s, %s, now())
           ON CONFLICT (squadra) DO UPDATE
               SET modulo = EXCLUDED.modulo,
                   slot = EXCLUDED.slot,
                   aggiornata_il = now();""",
        (nome_squadra, modulo, Json(slot)))
