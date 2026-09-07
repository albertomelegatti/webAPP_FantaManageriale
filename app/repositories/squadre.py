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


def sposta_crediti(cur, squadra_from: str, squadra_to: str, crediti_da_spostare: int) -> None:
    """Trasferisce crediti fra due squadre, dentro la transazione del chiamante.

    Non committa e non intercetta errori: se qualcosa fallisce, l'eccezione
    risale e il chiamante annulla l'intera operazione. E' cio' che rende lo
    spostamento atomico rispetto al resto - l'attivazione di un prestito, un
    riscatto - invece di un passo a se' stante che puo' restare a meta'.
    """
    cur.execute("UPDATE squadra SET crediti = crediti - %s WHERE nome = %s;",
                (crediti_da_spostare, squadra_from))
    cur.execute("UPDATE squadra SET crediti = crediti + %s WHERE nome = %s;",
                (crediti_da_spostare, squadra_to))


def nomi_diversi_da(cur, nome_squadra: str) -> list[dict]:
    """Le altre squadre, escluso Svincolato: i possibili interlocutori di uno
    scambio o di un prestito."""
    cur.execute(
        "SELECT nome FROM squadra WHERE nome <> %s AND nome <> 'Svincolato' ORDER BY nome;",
        (nome_squadra,))
    return cur.fetchall()
