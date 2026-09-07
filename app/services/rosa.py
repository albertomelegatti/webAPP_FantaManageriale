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

from app.domini.ruoli import pulisci_ruolo, ruolo_sort_key
from app.repositories import giocatori as giocatori_repo
from app.repositories import richieste as richieste_repo


def _componi(riga, con_richiesta: set) -> dict:
    return {
        "id": riga["id"],
        "nome": riga["nome"],
        "ruolo": pulisci_ruolo(riga["ruolo"]),
        "club": riga["club"],
        "quot_att_mantra": riga["quot_att_mantra"],
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


def giocatori_tagliabili(cur, nome_squadra: str) -> list[dict]:
    """I giocatori di cui la squadra detiene il cartellino, primavera esclusa:
    sono quelli che puo' tagliare."""
    return _elenco_ordinato(cur, giocatori_repo.con_cartellino(cur, nome_squadra))


def giocatori_primavera(cur, nome_squadra: str) -> list[dict]:
    return _elenco_ordinato(cur, giocatori_repo.primavera(cur, nome_squadra))
