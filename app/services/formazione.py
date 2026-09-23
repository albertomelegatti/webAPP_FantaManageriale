"""
Composizione della pagina "Formazione" (il campetto): l'editor privato per la
squadra proprietaria e la vista pubblica di sola lettura sulla pagina
squadra.
"""

from app.core.formato import url_campioncino
from app.domini import formazione_auto, moduli
from app.domini.ruoli import pulisci_ruolo
from app.repositories import formazione as formazione_repo
from app.repositories import giocatori as giocatori_repo


def _slot_vuoti(modulo: str) -> list[dict]:
    return [moduli.slot_vuoto() for _ in moduli.MODULI[modulo]]


def _slot_salvati(riga_formazione: dict, modulo: str) -> list[dict]:
    """Uno slot normalizzato per ogni posizione del modulo (vedi
    moduli.normalizza_slot per il formato vecchio a due riserve)."""
    salvati = riga_formazione["slot"] or []
    return [moduli.normalizza_slot(salvati[i] if i < len(salvati) else None)
            for i in range(len(moduli.MODULI[modulo]))]


def _rosa_attiva(cur, nome_squadra: str) -> list[dict]:
    """I giocatori schierabili: rosa titolare della squadra, Primavera esclusa
    (stesso gruppo gia' usato per valore_rosa/eta_media in
    app/services/dashboard.py)."""
    giocatori = giocatori_repo.collegati_alla_squadra(cur, nome_squadra)
    return [
        {
            "id": g["id"],
            "nome": g["nome"],
            "ruolo": pulisci_ruolo(g["ruolo"]),
            "club": g["club"],
            "campioncino": url_campioncino(g.get("id_fantacalcio")),
            # Solo per ordinare la proposta di formazione_auto.schiera(): il
            # picker manuale non la mostra, non serve altrove nell'editor.
            "quot_att_mantra": g["quot_att_mantra"],
        }
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


def dati_editor(cur, nome_squadra: str, modulo_richiesto: str | None, auto: bool = False) -> dict:
    """Tutto quello che serve alla pagina di modifica: rosa disponibile,
    modulo corrente e, per ogni slot, i candidati compatibili e la selezione
    attuale - quella salvata su database, o vuota se si sta provando un
    modulo diverso da quello salvato (cambiare modulo azzera la formazione
    non ancora salvata, stesso comportamento del simulatore di riferimento).

    auto=True (il bottone "Ottimizza"): la selezione di partenza non e' ne'
    quella salvata ne' vuota, ma la proposta di formazione_auto.schiera() -
    resta comunque solo una proposta, va confermata con "Salva formazione"
    come ogni altra modifica non ancora scritta su database.
    """
    rosa = _rosa_attiva(cur, nome_squadra)
    riga_salvata = formazione_repo.leggi(cur, nome_squadra)

    if modulo_richiesto and modulo_richiesto in moduli.MODULI:
        modulo = modulo_richiesto
        slot_salvati = _slot_vuoti(modulo)
    elif riga_salvata and riga_salvata["modulo"] in moduli.MODULI:
        modulo = riga_salvata["modulo"]
        slot_salvati = _slot_salvati(riga_salvata, modulo)
    else:
        modulo = moduli.MODULO_DEFAULT
        slot_salvati = _slot_vuoti(modulo)

    if auto:
        slot_salvati = formazione_auto.schiera(moduli.MODULI[modulo], rosa)

    # La rosa va alla pagina una volta sola, ordinata per nome: gli slot
    # citano solo gli id ammessi. Serve intera, non solo i candidati degli
    # slot, perche' anche chi non ha posto nel modulo compare fra i
    # panchinari sotto il campo.
    rosa = sorted(rosa, key=lambda g: g["nome"])
    righe_slot = []
    for indice, ruoli_slot in enumerate(moduli.MODULI[modulo]):
        righe_slot.append({
            "indice": indice,
            "etichetta": moduli.slot_label(ruoli_slot),
            "ammessi": [g["id"] for g in rosa if moduli.ruolo_compatibile(g["ruolo"], ruoli_slot)],
            "selezionati": slot_salvati[indice] if indice < len(slot_salvati) else moduli.slot_vuoto(),
        })

    return {
        "modulo": modulo,
        "moduli_disponibili": sorted(moduli.MODULI.keys()),
        "linee": _disponi_campo(modulo, righe_slot),
        "rosa": [{k: g[k] for k in ("id", "nome", "ruolo", "campioncino")} for g in rosa],
        "max_riserve": moduli.MAX_RISERVE,
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

    righe_slot = []
    schierati = set()
    for indice, valori in enumerate(_slot_salvati(riga_formazione, modulo)):
        schierati.update([valori["tit"], *valori["ris"]])
        righe_slot.append({
            "indice": indice,
            "etichetta": moduli.slot_label(moduli.MODULI[modulo][indice]),
            "titolare": per_id.get(valori["tit"]),
            "riserve": [per_id[r] for r in valori["ris"] if r in per_id],
        })

    # Chi e' in rosa ma non sta ne' in campo ne' in panchina di uno slot.
    # "schierabile": il modulo ha almeno uno slot per il suo ruolo (verde);
    # altrimenti nel modulo scelto non puo' proprio giocare (ambra).
    panchinari = [
        dict(g, schierabile=any(moduli.ruolo_compatibile(g["ruolo"], s) for s in moduli.MODULI[modulo]))
        for g in sorted(rosa, key=lambda g: g["nome"])
        if g["id"] not in schierati
    ]

    return {
        "modulo": modulo,
        "linee": _disponi_campo(modulo, righe_slot),
        "panchinari": panchinari,
    }


def salva(cur, nome_squadra: str, modulo: str, selezioni: dict[int, dict[str, str]]) -> list[str]:
    """Valida e salva la formazione; in caso di errori non scrive nulla e li
    ritorna (lista vuota se il salvataggio e' andato a buon fine).

    selezioni: {indice_slot: {"tit": "id"|"", "ris": ["id", ...]}}, gli id
    arrivano come stringhe dal form HTML; le riserve in ordine di chiamata.
    """
    if modulo not in moduli.MODULI:
        return ["Modulo non valido."]

    rosa = {str(g["id"]): g for g in _rosa_attiva(cur, nome_squadra)}

    errori = []
    usati = set()
    slot_finale = []

    def valida(indice: int, ruoli_slot: tuple[str, ...], id_scelto: str) -> int | None:
        giocatore = rosa.get(id_scelto)
        if giocatore is None:
            errori.append(f"Slot {indice + 1}: giocatore non in rosa.")
            return None
        if not moduli.ruolo_compatibile(giocatore["ruolo"], ruoli_slot):
            errori.append(f"Slot {indice + 1}: {giocatore['nome']} non gioca in {moduli.slot_label(ruoli_slot)}.")
            return None
        if id_scelto in usati:
            errori.append(f"{giocatore['nome']} è schierato più di una volta.")
            return None
        usati.add(id_scelto)
        return int(id_scelto)

    for indice, ruoli_slot in enumerate(moduli.MODULI[modulo]):
        valori = selezioni.get(indice, {})
        id_titolare = (valori.get("tit") or "").strip()
        id_riserve = [r.strip() for r in valori.get("ris") or [] if r and r.strip()]

        if len(id_riserve) > moduli.MAX_RISERVE:
            errori.append(f"Slot {indice + 1}: al massimo {moduli.MAX_RISERVE} riserve.")
            id_riserve = id_riserve[:moduli.MAX_RISERVE]
        if id_riserve and not id_titolare:
            errori.append(f"Slot {indice + 1}: ci sono riserve ma manca il titolare.")

        titolare = valida(indice, ruoli_slot, id_titolare) if id_titolare else None
        riserve = [valida(indice, ruoli_slot, r) for r in id_riserve]
        slot_finale.append({"tit": titolare, "ris": [r for r in riserve if r is not None]})

    if errori:
        return errori

    formazione_repo.salva(cur, nome_squadra, modulo, slot_finale)
    return []
