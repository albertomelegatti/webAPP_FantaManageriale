"""
Composizione della vista degli scambi.

Il problema che risolve: la pagina mercato interrogava il database una volta per
ogni riga di scambio, e piu' volte. Per ciascuna riga servivano i nomi dei
giocatori offerti e richiesti, la descrizione delle pick offerte e richieste, e
quella dei prestiti collegati: cinque interrogazioni per riga.

Peggio, la funzione che risolveva i nomi dei giocatori non riceveva la
connessione ma ne prelevava una propria dal pool, mentre la route ne teneva gia'
una. Misurato su una pagina con 17 scambi: 27 query e 23 checkout dal pool per
una sola richiesta.

Qui gli identificativi vengono raccolti da tutte le righe e risolti in blocco,
prima del ciclo. Il numero di query non dipende piu' da quanti scambi ci sono.
"""

from app.core.db import resync_sequence
from app.core.tempo import formatta_data
from app.repositories import draft as draft_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import prestiti as prestiti_repo
from app.repositories import prestiti as prestiti_repo_scritture
from app.repositories import scambi as scambi_repo


def _raccogli(righe, *campi) -> list:
    """Tutti gli identificativi che compaiono nei campi indicati, senza ripetizioni."""
    raccolti = set()
    for riga in righe:
        for campo in campi:
            raccolti.update(riga.get(campo) or [])
    return list(raccolti)


def _elenca(ids, mappa) -> str:
    """Nomi separati da virgola, nell'ordine in cui compaiono nello scambio.

    L'ordine e' quello scelto da chi ha proposto lo scambio, quindi va
    conservato: per questo si itera sugli id e non sul risultato della query.
    """
    if not ids:
        return ""
    return ", ".join(mappa.get(i, f"ID {i} (non trovato)") for i in ids)


def _elenca_pick(ids, mappa) -> str:
    if not ids:
        return ""
    return ", ".join(mappa[i] for i in ids if i in mappa)


def _smista_prestiti(ids, mappa, squadra_proponente) -> tuple[str, str]:
    """Separa i prestiti in offerti e richiesti secondo chi presta il giocatore."""
    offerti, richiesti = [], []
    for prestito_id in ids or []:
        descrizione = mappa.get(prestito_id)
        if not descrizione:
            continue
        destinazione = offerti if descrizione["squadra_prestante"] == squadra_proponente else richiesti
        destinazione.append(descrizione["testo"])
    return "\n".join(offerti), "\n".join(richiesti)


def _risolvi_riferimenti(cur, righe) -> tuple[dict, dict, dict]:
    """Le tre mappe di lookup, una query ciascuna a prescindere dal numero di righe."""
    nomi = giocatori_repo.nomi_per_id(
        cur, _raccogli(righe, "giocatori_offerti", "giocatori_richiesti"))
    pick = draft_repo.descrizioni_per_id(
        cur, _raccogli(righe, "pick_offerta", "pick_richiesta"))
    prestiti = prestiti_repo.descrizioni_per_id(
        cur, _raccogli(righe, "prestito_associato"))
    return nomi, pick, prestiti


def _componi(riga, nomi, pick, prestiti) -> dict:
    vista = dict(riga)
    vista["giocatori_offerti_nomi"] = _elenca(riga["giocatori_offerti"], nomi)
    vista["giocatori_richiesti_nomi"] = _elenca(riga["giocatori_richiesti"], nomi)
    vista["pick_offerta_nomi"] = _elenca_pick(riga["pick_offerta"], pick)
    vista["pick_richiesta_nomi"] = _elenca_pick(riga["pick_richiesta"], pick)
    offerti, richiesti = _smista_prestiti(
        riga["prestito_associato"], prestiti, riga["squadra_proponente"])
    vista["prestiti_offerti_formattati"] = offerti
    vista["prestiti_richiesti_formattati"] = richiesti
    return vista


def scambi_della_squadra(cur, nome_squadra: str) -> list[dict]:
    """Gli scambi della squadra, con nomi, pick e prestiti gia' risolti.

    Quattro query in tutto, qualunque sia il numero di scambi.
    """
    righe = scambi_repo.per_squadra(cur, nome_squadra)
    if not righe:
        return []
    nomi, pick, prestiti = _risolvi_riferimenti(cur, righe)
    return [_componi(riga, nomi, pick, prestiti) for riga in righe]


def dettaglio_proposta(cur, id_scambio) -> dict | None:
    """La singola proposta, nella forma attesa dalla pagina di dettaglio."""
    riga = scambi_repo.per_id(cur, id_scambio)
    if not riga:
        return None

    nomi, pick, prestiti = _risolvi_riferimenti(cur, [riga])
    offerti, richiesti = _smista_prestiti(
        riga["prestito_associato"], prestiti, riga["squadra_proponente"])

    return {
        "scambio_id": riga["id"],
        "squadra_proponente": riga["squadra_proponente"],
        "data_proposta": formatta_data(riga["data_proposta"]),
        "messaggio": riga["messaggio"],
        "stato": riga["stato"],
        "crediti_offerti": riga["crediti_offerti"],
        "crediti_richiesti": riga["crediti_richiesti"],
        "giocatori_offerti": _elenca(riga["giocatori_offerti"], nomi),
        "giocatori_richiesti": _elenca(riga["giocatori_richiesti"], nomi),
        "pick_offerta": _elenca_pick(riga["pick_offerta"], pick),
        "pick_richiesta": _elenca_pick(riga["pick_richiesta"], pick),
        "prestito_associato": (offerti, richiesti),
    }


def crea_proposta(conn, cur, proponente: str, proposta) -> int:
    """Crea la proposta e gli eventuali prestiti collegati, come un blocco solo.

    I prestiti nascono sospesi e referenziati dallo scambio: si attivano solo se
    la proposta viene accettata. Il costo di un prestito dentro uno scambio e'
    sempre zero, perche' il corrispettivo sta nei crediti dello scambio stesso.

    Le sequence vengono riallineate prima degli insert: import o restore manuali
    sul database possono averle lasciate indietro rispetto ai dati, ed e' la
    causa nota dei conflitti di chiave primaria su prestito e scambio.
    """
    resync_sequence(conn, 'prestito')

    id_prestiti = []
    for prestito, prestante, ricevente in (
            [(p, proposta.squadra_destinataria, proponente) for p in proposta.prestiti_richiesti]
            + [(p, proponente, proposta.squadra_destinataria) for p in proposta.prestiti_offerti]):
        id_prestiti.append(prestiti_repo_scritture.crea(
            cur, prestito.giocatore, prestante, ricevente, prestito.data_fine,
            "", 0, prestito.tipo, prestito.crediti_riscatto))

    resync_sequence(conn, 'scambio')

    return scambi_repo.crea(
        cur, proponente, proposta.squadra_destinataria,
        proposta.crediti_offerti, proposta.crediti_richiesti,
        proposta.giocatori_offerti, proposta.giocatori_richiesti,
        proposta.pick_offerta, proposta.pick_richiesta,
        proposta.messaggio, id_prestiti)
