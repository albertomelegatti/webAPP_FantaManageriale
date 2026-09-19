"""
Composizione della pagina "Formazione" (il campetto): l'editor privato per la
squadra proprietaria e la vista pubblica di sola lettura sulla pagina
squadra.
"""

from app.domini import moduli
from app.domini.ruoli import pulisci_ruolo
from app.repositories import formazione as formazione_repo
from app.repositories import giocatori as giocatori_repo


def _slot_vuoti(modulo: str) -> list[dict]:
    return [{"tit": None, "ris": None, "ter": None} for _ in moduli.MODULI[modulo]]


def _rosa_attiva(cur, nome_squadra: str) -> list[dict]:
    """I giocatori schierabili: rosa titolare della squadra, Primavera esclusa
    (stesso gruppo gia' usato per valore_rosa/eta_media in
    app/services/dashboard.py)."""
    giocatori = giocatori_repo.collegati_alla_squadra(cur, nome_squadra)
    return [
        {"id": g["id"], "nome": g["nome"], "ruolo": pulisci_ruolo(g["ruolo"]), "club": g["club"]}
        for g in giocatori
        if g["squadra_att"] == nome_squadra and g["tipo_contratto"] != "Primavera"
    ]


def _disponi_campo(modulo: str, righe_slot: list[dict]) -> list[list[dict]]:
    """Raggruppa gli slot in linee (portiere, difesa, centrocampo, attacco),
    ciascuna ordinata da sinistra a destra, con l'attacco in cima e il
    portiere in fondo - come un campo vero, con la propria porta in basso.
    """
    per_indice = {r["indice"]: r for r in righe_slot}
    linee_dimensioni = moduli.linee_modulo(modulo)

    gruppi = []
    i = 0
    for n in linee_dimensioni:
        pezzo = righe_slot[i:i + n]
        ordine = moduli.ordine_riga([(r["indice"], moduli.MODULI[modulo][r["indice"]]) for r in pezzo])
        gruppi.append([per_indice[indice] for indice in ordine])
        i += n

    gruppi.reverse()
    return gruppi


def dati_editor(cur, nome_squadra: str, modulo_richiesto: str | None) -> dict:
    """Tutto quello che serve alla pagina di modifica: rosa disponibile,
    modulo corrente e, per ogni slot, i candidati compatibili e la selezione
    attuale - quella salvata su database, o vuota se si sta provando un
    modulo diverso da quello salvato (cambiare modulo azzera la formazione
    non ancora salvata, stesso comportamento del simulatore di riferimento).
    """
    rosa = _rosa_attiva(cur, nome_squadra)
    riga_salvata = formazione_repo.leggi(cur, nome_squadra)

    if modulo_richiesto and modulo_richiesto in moduli.MODULI:
        modulo = modulo_richiesto
        slot_salvati = _slot_vuoti(modulo)
    elif riga_salvata and riga_salvata["modulo"] in moduli.MODULI:
        modulo = riga_salvata["modulo"]
        slot_salvati = riga_salvata["slot"] or _slot_vuoti(modulo)
    else:
        modulo = moduli.MODULO_DEFAULT
        slot_salvati = _slot_vuoti(modulo)

    righe_slot = []
    for indice, ruoli_slot in enumerate(moduli.MODULI[modulo]):
        valori = slot_salvati[indice] if indice < len(slot_salvati) else {}
        candidati = sorted(
            (g for g in rosa if moduli.ruolo_compatibile(g["ruolo"], ruoli_slot)),
            key=lambda g: g["nome"])
        righe_slot.append({
            "indice": indice,
            "etichetta": moduli.slot_label(ruoli_slot),
            "candidati": candidati,
            "selezionati": {posto: valori.get(posto) for posto in moduli.POSTI},
        })

    return {
        "modulo": modulo,
        "moduli_disponibili": sorted(moduli.MODULI.keys()),
        "linee": _disponi_campo(modulo, righe_slot),
        "posti": moduli.POSTI,
        "nome_posto": moduli.NOME_POSTO,
    }


def dati_pubblici(rosa: list[dict], riga_formazione: dict | None) -> dict | None:
    """Il campetto in sola lettura per la pagina pubblica della squadra.

    Non tocca il database: riusa i giocatori gia' letti per gli altri
    riquadri della pagina (elenchi["rosa"] di app/services/dashboard.py),
    incrociandoli con gli id salvati nella formazione. None se la squadra non
    ha ancora salvato nulla, o se il modulo salvato non esiste piu'.
    """
    if not riga_formazione:
        return None

    modulo = riga_formazione["modulo"]
    if modulo not in moduli.MODULI:
        return None

    per_id = {g["id"]: g for g in rosa}
    slot_salvati = riga_formazione["slot"] or []

    righe_slot = []
    for indice, ruoli_slot in enumerate(moduli.MODULI[modulo]):
        valori = slot_salvati[indice] if indice < len(slot_salvati) else {}
        righe_slot.append({
            "indice": indice,
            "etichetta": moduli.slot_label(ruoli_slot),
            "giocatori": {posto: per_id.get(valori.get(posto)) for posto in moduli.POSTI},
        })

    return {
        "modulo": modulo,
        "linee": _disponi_campo(modulo, righe_slot),
    }


def salva(cur, nome_squadra: str, modulo: str, selezioni: dict[int, dict[str, str]]) -> list[str]:
    """Valida e salva la formazione; in caso di errori non scrive nulla e li
    ritorna (lista vuota se il salvataggio e' andato a buon fine).

    selezioni: {indice_slot: {"tit": "id"|"", "ris": ..., "ter": ...}}, gli id
    arrivano come stringhe dal form HTML.
    """
    if modulo not in moduli.MODULI:
        return ["Modulo non valido."]

    rosa = {str(g["id"]): g for g in _rosa_attiva(cur, nome_squadra)}

    errori = []
    usati = set()
    slot_finale = []
    for indice, ruoli_slot in enumerate(moduli.MODULI[modulo]):
        valori = selezioni.get(indice, {})
        riga = {}
        for posto in moduli.POSTI:
            id_scelto = (valori.get(posto) or "").strip()
            if not id_scelto:
                riga[posto] = None
                continue
            giocatore = rosa.get(id_scelto)
            if giocatore is None:
                errori.append(f"Slot {indice + 1}: giocatore non in rosa.")
                riga[posto] = None
                continue
            if not moduli.ruolo_compatibile(giocatore["ruolo"], ruoli_slot):
                errori.append(f"Slot {indice + 1}: {giocatore['nome']} non gioca in {moduli.slot_label(ruoli_slot)}.")
                riga[posto] = None
                continue
            if id_scelto in usati:
                errori.append(f"{giocatore['nome']} è schierato più di una volta.")
                riga[posto] = None
                continue
            usati.add(id_scelto)
            riga[posto] = int(id_scelto)
        slot_finale.append(riga)

    if errori:
        return errori

    formazione_repo.salva(cur, nome_squadra, modulo, slot_finale)
    return []
