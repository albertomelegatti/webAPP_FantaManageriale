"""Sincronizzazione con Transfermarkt: cache locale e abbinamento ai giocatori."""


def ultimo_aggiornamento(cur):
    """Quando e' stata scritta per l'ultima volta la cache locale, o None se
    non e' mai stata popolata."""
    cur.execute("SELECT max(aggiornato_il) AS ultimo FROM transfermarkt_giocatori;")
    return cur.fetchone()["ultimo"]


def mappa_club(cur) -> dict[str, str]:
    """{club nel nostro database: nome del club su Transfermarkt}."""
    cur.execute("SELECT club, nome_transfermarkt FROM transfermarkt_mappa_club;")
    return {r["club"]: r["nome_transfermarkt"] for r in cur.fetchall()}


def svuota_cache(cur) -> None:
    """La cache locale viene ricreata da zero a ogni run: non ha senso
    accumulare gli scarti di dump precedenti."""
    cur.execute("TRUNCATE transfermarkt_giocatori;")


def inserisci_in_cache(cur, giocatore: dict) -> None:
    cur.execute(
        """INSERT INTO transfermarkt_giocatori
               (id_transfermarkt, club_tm, nome, cognome, data_nascita, scadenza_contratto, valore_mercato)
           VALUES (%s, %s, %s, %s, %s, %s, %s);""",
        (giocatore["id_transfermarkt"], giocatore["club_tm"], giocatore["nome"], giocatore["cognome"],
         giocatore["data_nascita"], giocatore["scadenza_contratto"], giocatore["valore_mercato"]))


def gia_mappati(cur) -> list[dict]:
    """I giocatori di prima fascia gia' abbinati: id_transfermarkt non viene
    mai ricalcolato per loro, solo i dati anagrafici vengono aggiornati."""
    cur.execute(
        "SELECT id, id_transfermarkt, data_nascita, scadenza_contratto, valore_mercato FROM giocatore "
        "WHERE id_transfermarkt IS NOT NULL AND priorita = 1;")
    return cur.fetchall()


def aggiorna_dati_sincronizzati(cur, id_giocatore: int, data_nascita, scadenza_contratto, valore_mercato) -> None:
    cur.execute(
        "UPDATE giocatore SET data_nascita = %s, scadenza_contratto = %s, valore_mercato = %s WHERE id = %s;",
        (data_nascita, scadenza_contratto, valore_mercato, id_giocatore))


def non_ancora_mappati(cur) -> list[dict]:
    """I giocatori di prima fascia senza un id Transfermarkt: candidati al
    primo abbinamento."""
    cur.execute("SELECT id, nome, club FROM giocatore WHERE id_transfermarkt IS NULL AND priorita = 1;")
    return cur.fetchall()


def assegna_abbinamento(cur, id_giocatore: int, candidato: dict) -> None:
    """Un solo candidato esatto: l'abbinamento e' certo, si scrive subito."""
    cur.execute(
        "UPDATE giocatore SET id_transfermarkt = %s, data_nascita = %s, scadenza_contratto = %s, "
        "valore_mercato = %s WHERE id = %s;",
        (candidato["id_transfermarkt"], candidato["data_nascita"], candidato["scadenza_contratto"],
         candidato["valore_mercato"], id_giocatore))


def segnala_candidati_ambigui(cur, id_giocatore: int, id_transfermarkt_candidati: list[int]) -> None:
    """Piu' candidati con lo stesso nome: si marca la cache per la revisione
    manuale invece di scegliere a caso."""
    cur.execute(
        "UPDATE transfermarkt_giocatori SET id_giocatore = %s WHERE id_transfermarkt = ANY(%s);",
        (id_giocatore, id_transfermarkt_candidati))


def segnala_non_trovato(cur, id_giocatore: int) -> None:
    """Nessun candidato: si registra il tentativo, cosi' compare fra le
    corrispondenze da verificare invece di sparire in silenzio."""
    cur.execute(
        "INSERT INTO transfermarkt_giocatori (id_giocatore, id_transfermarkt) VALUES (%s, NULL);",
        (id_giocatore,))


def id_giocatori_in_coda(cur) -> set[int]:
    """I giocatori con almeno una riga di cache marcata per la loro revisione."""
    cur.execute("SELECT DISTINCT id_giocatore FROM transfermarkt_giocatori WHERE id_giocatore IS NOT NULL;")
    return {r["id_giocatore"] for r in cur.fetchall()}


def rimuovi_dalla_coda(cur, id_giocatore: int) -> None:
    """Toglie il giocatore dalla coda di revisione, una volta risolto il caso.

    La riga sintetica "non trovato" (id_transfermarkt NULL) non serve piu' a
    nulla; le righe di candidati reali restano come cache, tornano solo a non
    essere piu' marcate per questo giocatore.
    """
    cur.execute(
        "DELETE FROM transfermarkt_giocatori WHERE id_giocatore = %s AND id_transfermarkt IS NULL;",
        (id_giocatore,))
    cur.execute(
        "UPDATE transfermarkt_giocatori SET id_giocatore = NULL WHERE id_giocatore = %s;",
        (id_giocatore,))


def candidato_per_id_transfermarkt(cur, id_transfermarkt) -> dict | None:
    """Un suggerimento fuzzy confermato dall'admin: non era marcato come
    candidato, va cercato in cache solo ora che viene confermato."""
    cur.execute(
        """SELECT id_transfermarkt, data_nascita, scadenza_contratto, valore_mercato
           FROM transfermarkt_giocatori WHERE id_transfermarkt = %s;""",
        (id_transfermarkt,))
    return cur.fetchone()


def candidato_per_giocatore(cur, id_giocatore: int, id_transfermarkt) -> dict | None:
    """Un candidato gia' marcato come tale per questo giocatore."""
    cur.execute(
        """SELECT id_transfermarkt, data_nascita, scadenza_contratto, valore_mercato
           FROM transfermarkt_giocatori WHERE id_giocatore = %s AND id_transfermarkt = %s;""",
        (id_giocatore, id_transfermarkt))
    return cur.fetchone()


def conferma_abbinamento(cur, id_giocatore: int, candidato: dict) -> None:
    cur.execute(
        """UPDATE giocatore
           SET id_transfermarkt = %s, data_nascita = %s, scadenza_contratto = %s, valore_mercato = %s
           WHERE id = %s;""",
        (candidato["id_transfermarkt"], candidato["data_nascita"],
         candidato["scadenza_contratto"], candidato["valore_mercato"], id_giocatore))


def da_rivedere(cur) -> list[dict]:
    """I giocatori con candidati o suggerimenti ancora da confermare, per la
    pagina di amministrazione."""
    cur.execute(
        """SELECT c.id_giocatore, g.nome, g.club, g.ruolo,
                  c.id_transfermarkt, c.nome AS nome_tm, c.cognome AS cognome_tm,
                  c.club_tm, c.data_nascita, c.scadenza_contratto
           FROM transfermarkt_giocatori c
           JOIN giocatore g ON g.id = c.id_giocatore
           WHERE c.id_giocatore IS NOT NULL
           ORDER BY g.nome, c.cognome;""")
    return cur.fetchall()


def rosa_per_club_tm(cur, club_tm: str) -> list[dict]:
    """La rosa in cache di un club, per calcolare suggerimenti fuzzy al volo."""
    cur.execute(
        """SELECT id_transfermarkt, nome, cognome, data_nascita, scadenza_contratto
           FROM transfermarkt_giocatori WHERE club_tm = %s;""",
        (club_tm,))
    return cur.fetchall()
