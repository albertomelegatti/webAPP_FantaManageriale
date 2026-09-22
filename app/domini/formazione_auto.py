"""
Schieramento automatico: il bottone "Ottimizza" nell'editor formazione
(user_formazione.html), che propone una formazione completa invece di
lasciare all'utente il compito di scegliere tutti gli undici titolari a
mano. Stesso algoritmo del simulatore di riferimento
(fanta-mantra/index.html, funzioni autofillBoard/placeByDefPriority),
riscritto sui ruoli e sull'ordinamento gia' in uso in questa app (vedi
RUOLI_BASE_ORDINE in app/domini/ruoli.py) invece di introdurne uno parallelo.

Funzioni pure, nessun accesso a database.
"""

from app.domini.ruoli import ruolo_base_sort_key


def _ruoli(ruolo: str) -> list[str]:
    return [r.strip() for r in (ruolo or "").split(",") if r.strip()]


def _ruoli_chiave(ruoli_giocatore: list[str]) -> set[str]:
    """Il ruolo piu' difensivo del giocatore (a parita' di ordinamento, tutti
    quelli a pari rango): e' l'unico che conta per l'assegnazione automatica,
    un giocatore Dd/E vale come un Dd, non come i due insieme - altrimenti un
    giocatore molto versatile finirebbe piazzato ovunque anche a scapito di
    chi ha davvero solo quel ruolo."""
    rango_minimo = min(ruolo_base_sort_key(r) for r in ruoli_giocatore)
    return {r for r in ruoli_giocatore if ruolo_base_sort_key(r) == rango_minimo}


def _ruoli_effettivi_slot(ruoli_slot: tuple[str, ...]) -> set[str]:
    """Il ruolo piu' offensivo ammesso dallo slot: uno slot M/C conta come C,
    non come i due insieme (stessa logica di _ruoli_chiave, specchiata)."""
    rango_massimo = max(ruolo_base_sort_key(r) for r in ruoli_slot)
    return {r for r in ruoli_slot if ruolo_base_sort_key(r) == rango_massimo}


def _combacia(ruoli_slot: tuple[str, ...], ruoli_giocatore: list[str]) -> bool:
    """Combacio esatto per l'automazione: il ruolo piu' difensivo del
    giocatore deve coincidere col ruolo piu' offensivo ammesso dallo slot.

    E' piu' severo del "sovrapposizione qualsiasi" di moduli.ruolo_compatibile
    (quello che alimenta il picker manuale, dove va bene mostrare piu' scelte
    possibili): qui serve, altrimenti un giocatore versatile sprecherebbe uno
    slot che gli sta larghissimo invece di lasciarlo a chi ne ha davvero
    bisogno.
    """
    return bool(_ruoli_chiave(ruoli_giocatore) & _ruoli_effettivi_slot(ruoli_slot))


def schiera(modulo: list[tuple[str, ...]], rosa: list[dict]) -> list[dict]:
    """Una proposta di formazione completa per il modulo dato.

    Ogni giocatore (dal piu' quotato) va nel ruolo piu' difensivo fra i suoi:
    prima titolare in uno slot libero che combacia - a parita' di combacio,
    il piu' specifico (meno ruoli ammessi), per non sprecare uno slot
    flessibile che potrebbe servire dopo a un giocatore meno versatile - poi,
    se non c'e' un titolare libero, riserva sotto lo slot compatibile con
    meno riserve gia' assegnate. Un giocatore senza nessuno slot compatibile
    nel modulo resta fuori, il chiamante lo trattera' come "fuori campo"
    (non e' un errore: succede con moduli che non prevedono il suo ruolo).

    rosa: [{"id", "ruolo" (stringa pulita "Dd,Ds"), "quot_att_mantra"}, ...].
    Ritorna una riga per slot dello stesso modulo, stesso formato di
    _slot_vuoti in app/services/formazione.py:
    [{"tit": id|None, "ris": id|None, "ter": id|None}, ...].
    """
    righe = [{"tit": None, "ris": None, "ter": None} for _ in modulo]

    ordinata = sorted(rosa, key=lambda g: g.get("quot_att_mantra") or 0, reverse=True)

    for giocatore in ordinata:
        ruoli_giocatore = _ruoli(giocatore.get("ruolo"))
        if not ruoli_giocatore:
            continue

        candidati = [i for i, ruoli_slot in enumerate(modulo)
                     if _combacia(ruoli_slot, ruoli_giocatore)]
        if not candidati:
            continue

        liberi = [i for i in candidati if righe[i]["tit"] is None]
        if liberi:
            liberi.sort(key=lambda i: len(modulo[i]))
            righe[liberi[0]]["tit"] = giocatore["id"]
            continue

        occupati = [i for i in candidati if righe[i]["tit"] is not None]
        occupati.sort(key=lambda i: (righe[i]["ris"] is not None) + (righe[i]["ter"] is not None))
        for i in occupati:
            if righe[i]["ris"] is None:
                righe[i]["ris"] = giocatore["id"]
                break
            if righe[i]["ter"] is None:
                righe[i]["ter"] = giocatore["id"]
                break

    return righe
