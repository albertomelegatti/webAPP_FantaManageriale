"""
Composizione delle viste di rosa: prima squadra e primavera.

Il problema che risolve: entrambe le pagine costruivano l'elenco dei giocatori
chiedendo, per ognuno, se avesse gia' una richiesta di modifica contratto
aperta. Una interrogazione per giocatore, dentro il ciclo di rendering. Sulla
rosa piu' numerosa del campionato, 33 giocatori, la pagina dei tagli costava 36
query.

Qui gli identificativi vengono raccolti prima e la domanda si fa una volta sola,
per tutti.
"""

from app.core.formato import url_campioncino
from app.core.tempo import aggiungi_mesi, oggi
from app.domini.ruoli import pulisci_ruolo, ruolo_sort_key
from app.repositories import giocatori as giocatori_repo
from app.repositories import richieste as richieste_repo
from app.repositories import storico_rosa as storico_rosa_repo

# Un giocatore della prima squadra si puo' tagliare solo dopo questi mesi di
# permanenza in rosa, contati dall'arrivo (vedi giocatore_storico). Il taglio
# dalla Primavera non ha questo vincolo.
MESI_MINIMI_PRIMA_DEL_TAGLIO = 4


def _componi(riga, con_richiesta: set) -> dict:
    return {
        "id": riga["id"],
        "nome": riga["nome"],
        "ruolo": pulisci_ruolo(riga["ruolo"]),
        "club": riga["club"],
        "quot_att_mantra": riga["quot_att_mantra"],
        "campioncino": url_campioncino(riga.get("id_fantacalcio")),
        "esiste_gia_una_richiesta": riga["id"] in con_richiesta,
    }


def _elenco_ordinato(cur, righe) -> list[dict]:
    """Vista dei giocatori, ordinata per ruolo, con una sola interrogazione
    sulle richieste aperte a prescindere da quanti giocatori ci sono."""
    if not righe:
        return []
    con_richiesta = richieste_repo.id_con_richiesta_in_elaborazione(
        cur, [r["id"] for r in righe])
    elenco = [_componi(r, con_richiesta) for r in righe]
    elenco.sort(key=lambda g: ruolo_sort_key(g["ruolo"]))
    return elenco


def _sblocco_taglio(dal):
    """Il primo giorno in cui il giocatore si puo' tagliare, o None se lo si
    puo' gia' fare. Senza data di arrivo nota il taglio non si blocca: non c'e'
    modo di sapere da quanto e' in rosa.

    `dal` e' in ora italiana "nominale" (vedi giocatore_storico): la sua data
    e' gia' quella di Roma, senza conversioni.
    """
    if dal is None:
        return None
    sblocco = aggiungi_mesi(dal.date(), MESI_MINIMI_PRIMA_DEL_TAGLIO)
    return sblocco if oggi() < sblocco else None


def taglio_bloccato_fino_a(cur, id_giocatore):
    """Il giorno da cui il giocatore si potra' tagliare, o None se si puo' gia'."""
    return _sblocco_taglio(storico_rosa_repo.arrivi(cur, [id_giocatore]).get(int(id_giocatore)))


def giocatori_tagliabili(cur, nome_squadra: str) -> list[dict]:
    """I giocatori di cui la squadra detiene il cartellino, primavera esclusa:
    sono quelli che puo' tagliare. `tagliabile_dal` e' valorizzato per chi e'
    in rosa da troppo poco per essere tagliato."""
    elenco = _elenco_ordinato(cur, giocatori_repo.con_cartellino(cur, nome_squadra))
    arrivi = storico_rosa_repo.arrivi(cur, [g["id"] for g in elenco])
    for g in elenco:
        g["tagliabile_dal"] = _sblocco_taglio(arrivi.get(g["id"]))
    return elenco


def giocatori_primavera(cur, nome_squadra: str) -> list[dict]:
    return _elenco_ordinato(cur, giocatori_repo.primavera(cur, nome_squadra))
