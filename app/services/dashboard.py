"""
Composizione della dashboard di una squadra.

E' la pagina piu' pesante dell'applicazione ed e' quella su cui atterra ogni
utente per la propria squadra. Costava dieci query, e su questo database il
tempo di una pagina e' quasi interamente il numero di viaggi di rete: una query
banale costa ~36 ms, una complessa ~40. Ridurre il numero di interrogazioni vale
molto piu' che renderle piu' furbe.

Le dieci diventano cinque, senza cambiare nulla di cio' che la pagina mostra:
- i quattro elenchi di giocatori arrivavano da quattro query sulla stessa
  tabella con filtri diversi: ora e' una sola, divisa in memoria
- squadra e stadio erano due letture su tabelle in rapporto uno a uno: una JOIN
- gli slot occupati da giocatori erano un conteggio a parte, ma si ricavano
  dalle righe gia' lette: resta da chiedere al database solo quelli impegnati
  in aste
"""

from app.core.tempo import (formatta_data_nascita_con_eta,
                            formatta_scadenza_contratto)
from app.domini.ruoli import pulisci_ruolo, ruolo_sort_key
from app.repositories import aste as aste_repo
from app.repositories import draft as draft_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories.giocatori import CONTRATTI_CHE_OCCUPANO_SLOT
from app.repositories import movimenti as movimenti_repo
from app.repositories import squadre as squadre_repo

# Contratti che rappresentano un giocatore prestato ad altri pur restando di
# proprieta' della squadra.
CONTRATTI_IN_USCITA = ('Fanta-Prestito', 'Prestito Reale')

NON_SINCRONIZZATO = "Non sincronizzata"


def _ordina(giocatori: list[dict]) -> list[dict]:
    """Per ruolo, e a parita' di ruolo per nome.

    Il nome come secondo criterio non e' un dettaglio estetico: prima
    l'ordinamento era solo per ruolo, quindi due giocatori dello stesso ruolo
    comparivano nell'ordine in cui il database restituiva le righe - che non e'
    garantito e cambia col piano di esecuzione. La stessa pagina poteva quindi
    mostrare la rosa in ordini diversi senza che nulla fosse cambiato.
    """
    return sorted(giocatori, key=lambda g: (ruolo_sort_key(g["ruolo"]), g["nome"]))


def _riga_rosa(g: dict) -> dict:
    return {
        "nome": g["nome"],
        "tipo_contratto": g["tipo_contratto"],
        "ruolo": pulisci_ruolo(g["ruolo"]),
        "quot_att_mantra": g["quot_att_mantra"],
        "costo": g["costo"],
        "club": g["club"],
        "squadra_att": g["squadra_att"],
        "squadra_username": g["squadra_username"],
        "detentore_cartellino": g["detentore_cartellino"],
        "detentore_username": g["detentore_username"],
        "data_nascita": formatta_data_nascita_con_eta(g["data_nascita"]) or NON_SINCRONIZZATO,
        "scadenza_contratto_reale": formatta_scadenza_contratto(g["scadenza_contratto"]) or NON_SINCRONIZZATO,
    }


def _riga_breve(g: dict, *campi: str) -> dict:
    riga = {"nome": g["nome"], "ruolo": pulisci_ruolo(g["ruolo"]),
            "quot_att_mantra": g["quot_att_mantra"]}
    riga.update({c: g[c] for c in campi})
    return riga


def _dividi_giocatori(giocatori: list[dict], nome_squadra: str) -> dict:
    """I quattro elenchi della pagina, ricavati da un unico insieme di righe.

    Nota: i prestiti in entrata compaiono anche nella rosa, perche' la rosa
    esclude solo la primavera. E' il comportamento che la pagina ha sempre
    avuto e viene conservato.
    """
    in_rosa = [g for g in giocatori if g["squadra_att"] == nome_squadra]

    return {
        "rosa": _ordina([_riga_rosa(g) for g in in_rosa
                         if g["tipo_contratto"] != "Primavera"]),
        "primavera": _ordina([_riga_breve(g) for g in in_rosa
                              if g["tipo_contratto"] == "Primavera"]),
        "prestiti_in": _ordina([_riga_breve(g, "detentore_cartellino") for g in in_rosa
                                if g["tipo_contratto"] == "Fanta-Prestito"]),
        "prestiti_out": _ordina([_riga_breve(g, "squadra_att") for g in giocatori
                                 if g["detentore_cartellino"] == nome_squadra
                                 and g["tipo_contratto"] in CONTRATTI_IN_USCITA]),
    }


def _pick(righe: list[dict]) -> list[dict]:
    return [{
        "detentore_originale": p["detentore_originale"],
        # anno e' una data sul database, in pagina si mostra solo l'anno
        "anno": p["anno"].year if hasattr(p["anno"], "year") else p["anno"],
        "numero": p["numero"],
        "giocatore_scelto": p["giocatore_scelto"] or "—",
    } for p in righe]


def dati_squadra(cur, nome_squadra: str) -> dict | None:
    """Tutto quello che serve alla pagina, in cinque query.

    None se la squadra non esiste.
    """
    squadra = squadre_repo.con_stadio(cur, nome_squadra)
    if not squadra:
        return None

    giocatori = giocatori_repo.collegati_alla_squadra(cur, nome_squadra)
    elenchi = _dividi_giocatori(giocatori, nome_squadra)

    # Gli slot occupati da giocatori sotto contratto si contano sulle righe che
    # abbiamo gia' in memoria: non serve chiederlo al database.
    slot_giocatori = sum(1 for g in giocatori
                         if g["squadra_att"] == nome_squadra
                         and g["tipo_contratto"] in CONTRATTI_CHE_OCCUPANO_SLOT)
    slot_aste = aste_repo.slot_impegnati(cur, nome_squadra)

    stadio = None
    if squadra["stadio_nome"] is not None:
        stadio = {"nome": squadra["stadio_nome"],
                  "proprietario": squadra["stadio_proprietario"],
                  "livello": squadra["stadio_livello"]}

    return {
        "username": squadra["username"],
        "crediti": squadra["crediti"],
        "stadio": stadio,
        "slot_occupati": slot_giocatori + slot_aste,
        "slot_giocatori": slot_giocatori,
        "prestiti_in_num": len(elenchi["prestiti_in"]),
        "draft_pick": _pick(draft_repo.pick_della_squadra(cur, nome_squadra)),
        "mercato": movimenti_repo.per_squadra(cur, nome_squadra),
        **elenchi,
    }
