"""
Moduli Mantra: gli 11 schemi tattici ammessi e i ruoli che ogni posizione
accetta.

Funzioni pure, nessun accesso a database. Ogni modulo è una lista di 11 slot,
in ordine (portiere, poi difesa, centrocampo, attacco); ogni slot è una tupla
di ruoli Mantra ammessi in quella posizione - es. ("A", "Pc") significa
"attaccante esterno o punta centrale". Stessi 11 moduli e stessa definizione
degli slot del simulatore di riferimento (fanta-mantra/engine.py), con "P"
tradotto in "Por" per allinearsi al codice ruolo di questa app
(vedi app/domini/ruoli.py).
"""

MODULI: dict[str, list[tuple[str, ...]]] = {
    "3-4-3":   [("Por",), ("Dc",), ("Dc",), ("Dc", "B"),
                ("E",), ("M", "C"), ("C",), ("E",),
                ("W", "A"), ("W", "A"), ("A", "Pc")],
    "3-4-1-2": [("Por",), ("Dc",), ("Dc",), ("Dc", "B"),
                ("E",), ("M", "C"), ("C",), ("E",),
                ("T",), ("A", "Pc"), ("A", "Pc")],
    "3-4-2-1": [("Por",), ("Dc",), ("Dc",), ("Dc", "B"),
                ("M",), ("M", "C"), ("E",), ("E", "W"),
                ("T",), ("T", "A"), ("A", "Pc")],
    "3-5-2":   [("Por",), ("Dc",), ("Dc",), ("Dc", "B"),
                ("M",), ("M", "C"), ("E",), ("E", "W"), ("C",),
                ("A", "Pc"), ("A", "Pc")],
    "3-5-1-1": [("Por",), ("Dc",), ("Dc",), ("Dc", "B"),
                ("M",), ("M",), ("C",), ("E", "W"), ("E", "W"),
                ("T", "A"), ("A", "Pc")],
    "4-3-3":   [("Por",), ("Dd",), ("Dc",), ("Dc",), ("Ds",),
                ("M", "C"), ("M",), ("C",),
                ("W", "A"), ("W", "A"), ("A", "Pc")],
    "4-3-1-2": [("Por",), ("Dd",), ("Dc",), ("Dc",), ("Ds",),
                ("M", "C"), ("M",), ("C",),
                ("T",), ("T", "A", "Pc"), ("A", "Pc")],
    "4-4-2":   [("Por",), ("Dd",), ("Dc",), ("Dc",), ("Ds",),
                ("M", "C"), ("E",), ("E", "W"), ("C",),
                ("A", "Pc"), ("A", "Pc")],
    "4-1-4-1": [("Por",), ("Dd",), ("Dc",), ("Dc",), ("Ds",),
                ("M",), ("C", "T"), ("T",), ("E", "W"), ("W",),
                ("A", "Pc")],
    "4-4-1-1": [("Por",), ("Dd",), ("Dc",), ("Dc",), ("Ds",),
                ("M",), ("C",), ("E", "W"), ("E", "W"),
                ("T", "A"), ("A", "Pc")],
    "4-2-3-1": [("Por",), ("Dd",), ("Dc",), ("Dc",), ("Ds",),
                ("M",), ("M", "C"), ("W", "T"), ("T",), ("W", "A"),
                ("A", "Pc")],
}

MODULO_DEFAULT = "4-4-2"

# Quante riserve puo' avere ogni slot, in ordine di chiamata. Stesso limite
# del Campetto Lega (github.com/andreamurari/fantamantra-campetti).
MAX_RISERVE = 4


def slot_vuoto() -> dict:
    return {"tit": None, "ris": []}


def normalizza_slot(valori: dict | None) -> dict:
    """Uno slot salvato nel formato corrente {"tit": id|None, "ris": [id, ...]}.

    Le formazioni salvate prima delle 4 riserve hanno invece due posti fissi,
    {"tit", "ris", "ter"} con un id (o None) ciascuno: si leggono come una
    panchina di due, nello stesso ordine, senza bisogno di migrare il JSONB.
    """
    valori = valori or {}
    ris = valori.get("ris")
    if isinstance(ris, list):
        riserve = [r for r in ris if r is not None]
    else:
        riserve = [r for r in (ris, valori.get("ter")) if r is not None]
    return {"tit": valori.get("tit"), "ris": riserve[:MAX_RISERVE]}


def linee_modulo(nome: str) -> list[int]:
    """'4-3-1-2' -> [1, 4, 3, 1, 2]: portiere piu' le linee nel nome."""
    return [1] + [int(x) for x in nome.split("-")]


def slot_label(slot: tuple[str, ...]) -> str:
    return "/".join(slot)


def ruolo_compatibile(ruolo_giocatore: str, slot: tuple[str, ...]) -> bool:
    """Vero se il giocatore ha almeno uno dei ruoli ammessi dallo slot.

    ruolo_giocatore e' la stringa grezza pulita da pulisci_ruolo (vedi
    app/domini/ruoli.py), es. "Dd,Dc".
    """
    ruoli = {r.strip() for r in (ruolo_giocatore or "").split(",") if r.strip()}
    return bool(ruoli & set(slot))


def ordine_riga(indici_ruoli: list[tuple[int, tuple[str, ...]]]) -> list[int]:
    """Riordina gli indici di slot di una riga da sinistra a destra sul campo.

    I terzini vanno sul loro lato (Ds a sinistra, Dd a destra); i ruoli
    centrali restano al centro; gli esterni senza lato fisso (E, W) si
    alternano fra i due lati. Stessa euristica del campetto di riferimento
    (fanta-mantra/static/app.js, disponiLinea).
    """
    def laterale(ruoli: tuple[str, ...]) -> bool:
        return any(r in ruoli for r in ("Ds", "Dd", "E", "W"))

    sinistra: list[int] = []
    destra: list[int] = []
    centro: list[int] = []
    neutri: list[int] = []
    for indice, ruoli in indici_ruoli:
        if not laterale(ruoli):
            centro.append(indice)
        elif "Ds" in ruoli:
            sinistra.append(indice)
        elif "Dd" in ruoli:
            destra.append(indice)
        else:
            neutri.append(indice)

    for i, indice in enumerate(neutri):
        (sinistra if i % 2 == 0 else destra).append(indice)

    return sinistra + centro + list(reversed(destra))
