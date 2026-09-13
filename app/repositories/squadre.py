"""Squadre: crediti e loro movimenti."""


def crediti(cur, nome_squadra: str) -> int:
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    return cur.fetchone()["crediti"]


def crediti_se_esiste(cur, nome_squadra: str) -> int | None:
    """Come crediti(), ma None se la squadra non esiste invece di sollevare.

    Serve nei punti che finora controllavano esplicitamente l'esistenza della
    riga prima di leggerne i crediti.
    """
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    riga = cur.fetchone()
    return riga["crediti"] if riga else None


def username(cur, nome_squadra: str) -> str:
    cur.execute("SELECT username FROM squadra WHERE nome = %s;", (nome_squadra,))
    return cur.fetchone()["username"]


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


def crediti_bloccando(cur, nome_squadra: str) -> int:
    """Come crediti(), ma blocca la riga: usata mentre si verifica se uno
    scambio e' ancora eseguibile."""
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s FOR UPDATE;", (nome_squadra,))
    return cur.fetchone()["crediti"]


def scambia_crediti(cur, nome_squadra: str, crediti_in_uscita: int, crediti_in_entrata: int) -> None:
    """Applica in un solo update sia i crediti ceduti sia quelli ricevuti in
    uno scambio: una squadra puo' offrire e ricevere crediti nella stessa
    transazione."""
    cur.execute(
        "UPDATE squadra SET crediti = crediti - %s + %s WHERE nome = %s;",
        (crediti_in_uscita, crediti_in_entrata, nome_squadra))


def imposta_crediti(cur, nome_squadra: str, nuovo_credito: int) -> None:
    cur.execute("UPDATE squadra SET crediti = %s WHERE nome = %s;", (nuovo_credito, nome_squadra))


def aggiungi_crediti(cur, nome_squadra: str, crediti: int) -> None:
    """Aggiunge (o, se negativo, sottrae) crediti alla squadra indicata."""
    cur.execute("UPDATE squadra SET crediti = crediti + %s WHERE nome = %s;", (crediti, nome_squadra))


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


def nomi(cur) -> list[str]:
    """I nomi delle squadre in gioco, in ordine alfabetico.

    'Svincolato' e' una riga della tabella `squadra` ma non e' una squadra:
    tiene i giocatori senza proprietario, e non va mai offerta in un elenco.
    """
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome;")
    return [riga["nome"] for riga in cur.fetchall()]


def nomi_e_username(cur) -> list[dict]:
    """Le squadre in gioco con il loro username, per la schermata di scelta."""
    cur.execute("SELECT nome, username FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome ASC;")
    return cur.fetchall()


def nomi_e_crediti(cur) -> list[dict]:
    """Le squadre in gioco con i loro crediti, per la pagina crediti/stadi/slot."""
    cur.execute("SELECT nome, crediti FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome ASC;")
    return cur.fetchall()


def nomi_diversi_da(cur, nome_squadra: str) -> list[dict]:
    """Le altre squadre, escluso Svincolato: i possibili interlocutori di uno
    scambio o di un prestito."""
    cur.execute(
        "SELECT nome FROM squadra WHERE nome <> %s AND nome <> 'Svincolato' ORDER BY nome;",
        (nome_squadra,))
    return cur.fetchall()


def con_stadio(cur, nome_squadra: str) -> dict | None:
    """Dati della squadra e del suo stadio in una query sola.

    Lo stadio e' in rapporto uno a uno con la squadra (proprietario e' unique),
    quindi non c'e' ragione di leggerli separatamente. LEFT JOIN perche' una
    squadra senza stadio deve comunque comparire.
    """
    cur.execute(
        """SELECT s.username, s.crediti,
                  st.nome AS stadio_nome, st.proprietario AS stadio_proprietario,
                  st.livello AS stadio_livello
           FROM squadra s
           LEFT JOIN stadio st ON st.proprietario = s.nome
           WHERE s.nome = %s;""",
        (nome_squadra,))
    return cur.fetchone()
