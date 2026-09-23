"""Sincronizzazione con fantacalcio.it: cache locale e abbinamento ai giocatori."""

from app.domini.matching_fantacalcio import NESSUNA_CORRISPONDENZA


def ultimo_aggiornamento(cur):
    """Quando e' stata scritta per l'ultima volta la cache locale, o None se
    non e' mai stata popolata."""
    cur.execute("SELECT max(aggiornato_il) AS ultimo FROM fantacalcio_giocatori;")
    return cur.fetchone()["ultimo"]


def svuota_cache(cur) -> None:
    """La cache locale viene ricreata da zero a ogni sincronizzazione: non ha
    senso accumulare gli scarti dei dump precedenti."""
    cur.execute("TRUNCATE fantacalcio_giocatori;")


def inserisci_in_cache(cur, giocatore: dict) -> None:
    cur.execute(
        """INSERT INTO fantacalcio_giocatori (id_fantacalcio, nome, squadra_fc)
           VALUES (%s, %s, %s);""",
        (giocatore["id_fantacalcio"], giocatore["nome"], giocatore["squadra_fc"]))


def non_ancora_mappati(cur) -> list[dict]:
    """I giocatori senza un id fantacalcio vero, di ogni priorita': mai
    abbinati (NULL) o segnati "nessuna corrispondenza" dall'admin, che
    restano candidati a un abbinamento certo se nel frattempo compaiono nel
    listone."""
    cur.execute(
        """SELECT id, nome, club, priorita, id_fantacalcio FROM giocatore
           WHERE id_fantacalcio IS NULL OR id_fantacalcio = %s;""",
        (NESSUNA_CORRISPONDENZA,))
    return cur.fetchall()


def mappati_in_listone(cur) -> list[dict]:
    """I giocatori di prima fascia (nel listone) gia' abbinati a un id vero:
    per ricontrollare che quell'id ci sia ancora nel listone scaricato."""
    cur.execute("SELECT id, nome, id_fantacalcio FROM giocatore WHERE id_fantacalcio > 0 AND priorita = 1;")
    return cur.fetchall()


def assegna_abbinamento(cur, id_giocatore: int, id_fantacalcio: int) -> None:
    """Un solo candidato esatto: l'abbinamento e' certo, si scrive subito."""
    cur.execute("UPDATE giocatore SET id_fantacalcio = %s WHERE id = %s;", (id_fantacalcio, id_giocatore))


def segnala_candidati_ambigui(cur, id_giocatore: int, id_fantacalcio_candidati: list[int]) -> None:
    """Piu' candidati con lo stesso nome: si marca la cache per la revisione
    manuale invece di scegliere a caso."""
    cur.execute(
        "UPDATE fantacalcio_giocatori SET id_giocatore = %s WHERE id_fantacalcio = ANY(%s);",
        (id_giocatore, id_fantacalcio_candidati))


def segnala_non_trovato(cur, id_giocatore: int) -> None:
    """Nessun candidato: si registra il tentativo, cosi' compare fra le
    corrispondenze da verificare invece di sparire in silenzio."""
    cur.execute(
        "INSERT INTO fantacalcio_giocatori (id_giocatore, id_fantacalcio) VALUES (%s, NULL);",
        (id_giocatore,))


def id_giocatori_in_coda(cur) -> set[int]:
    """I giocatori con almeno una riga di cache marcata per la loro revisione."""
    cur.execute("SELECT DISTINCT id_giocatore FROM fantacalcio_giocatori WHERE id_giocatore IS NOT NULL;")
    return {r["id_giocatore"] for r in cur.fetchall()}


def rimuovi_dalla_coda(cur, id_giocatore: int) -> None:
    """Toglie il giocatore dalla coda di revisione, una volta risolto il caso.

    La riga sintetica "non trovato" (id_fantacalcio NULL) non serve piu' a
    nulla; le righe di candidati reali restano come cache, tornano solo a non
    essere piu' marcate per questo giocatore.
    """
    cur.execute(
        "DELETE FROM fantacalcio_giocatori WHERE id_giocatore = %s AND id_fantacalcio IS NULL;",
        (id_giocatore,))
    cur.execute(
        "UPDATE fantacalcio_giocatori SET id_giocatore = NULL WHERE id_giocatore = %s;",
        (id_giocatore,))


def candidato_per_giocatore(cur, id_giocatore: int, id_fantacalcio: int) -> dict | None:
    """Un candidato gia' marcato come tale per questo giocatore."""
    cur.execute(
        "SELECT id_fantacalcio FROM fantacalcio_giocatori WHERE id_giocatore = %s AND id_fantacalcio = %s;",
        (id_giocatore, id_fantacalcio))
    return cur.fetchone()


def esiste_in_cache(cur, id_fantacalcio: int) -> bool:
    """Una scelta manuale (dalla ricerca sui "non trovati", non marcata per
    nessun giocatore in particolare): valida solo se l'id esiste ancora nel
    dump piu' recente, es. non e' stato rigenerato da una sincronizzazione nel
    frattempo."""
    cur.execute("SELECT 1 FROM fantacalcio_giocatori WHERE id_fantacalcio = %s;", (id_fantacalcio,))
    return cur.fetchone() is not None


def tutti_in_cache(cur) -> list[dict]:
    """L'intero dump scaricato, per popolare la ricerca manuale nella pagina
    di revisione quando non c'e' nessun candidato automatico."""
    cur.execute("SELECT id_fantacalcio, nome, squadra_fc FROM fantacalcio_giocatori WHERE id_fantacalcio IS NOT NULL;")
    return cur.fetchall()


def conferma_abbinamento(cur, id_giocatore: int, id_fantacalcio: int) -> None:
    cur.execute("UPDATE giocatore SET id_fantacalcio = %s WHERE id = %s;", (id_fantacalcio, id_giocatore))


def segna_nessuna_corrispondenza(cur, id_giocatore: int) -> None:
    """L'admin ha verificato che il giocatore non e' su fantacalcio.it: resta
    senza campioncino e non torna in coda alla prossima sincronizzazione."""
    cur.execute("UPDATE giocatore SET id_fantacalcio = %s WHERE id = %s;", (NESSUNA_CORRISPONDENZA, id_giocatore))


def da_rivedere(cur) -> list[dict]:
    """I giocatori con candidati ancora da confermare, per la pagina di
    amministrazione."""
    cur.execute(
        """SELECT c.id_giocatore, g.nome, g.club, g.ruolo,
                  c.id_fantacalcio, c.nome AS nome_fc, c.squadra_fc
           FROM fantacalcio_giocatori c
           JOIN giocatore g ON g.id = c.id_giocatore
           WHERE c.id_giocatore IS NOT NULL
           ORDER BY g.nome, c.nome;""")
    return cur.fetchall()
