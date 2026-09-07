"""Squadre: crediti e loro movimenti."""


def crediti(cur, nome_squadra: str) -> int:
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    return cur.fetchone()["crediti"]


def crediti_e_offerta(cur, nome_squadra: str) -> tuple[int, int]:
    """Crediti della squadra e totale impegnato in aste attive, in un'unica query.

    Le due informazioni servono sempre insieme (i crediti spendibili sono la
    differenza), quindi chiederle separatamente costerebbe due round-trip.
    """
    cur.execute(
        """
        SELECT
            (SELECT crediti FROM squadra WHERE nome = %s) AS crediti,
            (SELECT COALESCE(SUM(ultima_offerta), 0) FROM asta
                WHERE squadra_vincente = %s AND stato = 'in_corso') AS offerta_totale;
        """,
        (nome_squadra, nome_squadra),
    )
    riga = cur.fetchone()
    return riga["crediti"], riga["offerta_totale"]


def sposta_crediti(conn, squadra_from: str, squadra_to: str, crediti_da_spostare: int) -> None:
    """Trasferisce crediti fra due squadre.

    ATTENZIONE - difetto noto, correzione prevista nella Fase 8.
    A differenza di tutto il resto del pacchetto questa funzione riceve la
    connessione e committa al proprio interno, committando cosi' la transazione
    del CHIAMANTE. In attiva_prestito viene invocata prima del commit finale:
    un errore fra le due lascia i crediti spostati e il prestito non attivato.
    La correzione e' ricevere un cursore e non committare, come le altre; e'
    rimandata perche' cambia il comportamento. Vedi il test xfail(strict=True)
    in tests/test_scrittura_prestiti.py.
    """
    from app.core.logging import get_logger

    logger = get_logger(__name__)
    cur = None
    try:
        cur = conn.cursor()
        cur.execute("UPDATE squadra SET crediti = crediti - %s WHERE nome = %s;",
                    (crediti_da_spostare, squadra_from))
        cur.execute("UPDATE squadra SET crediti = crediti + %s WHERE nome = %s;",
                    (crediti_da_spostare, squadra_to))
        conn.commit()
    except Exception:
        logger.exception("Errore durante lo spostamento dei crediti")
        conn.rollback()
    finally:
        if cur:
            cur.close()
