"""Albo d'oro e stadi: validazione dei dati inseriti dall'admin.

Funzioni pure, nessun accesso a database: sollevano ErroreDominio con un
messaggio mostrabile, cosi' la route deve solo tradurlo in un flash.
"""

import re

from app.core.errori import ErroreDominio

LIVELLO_STADIO_MAX = 8  # stessa scala di RENDITA_STADIO in services/crediti_stadi_slot.py
POSIZIONE_MAX = 30
LUNGHEZZA_FASE_MAX = 40
LUNGHEZZA_NOME_STADIO_MAX = 60
RENDITA_MAX = 1000  # solo un freno ai refusi: la scala vera e' nel regolamento

FASI_COPPA_STANDARD = ("Final 4", "Girone A", "Girone B")
SLOT_FASE_FINALE = 2  # campione e finalista, come nelle stagioni gia' registrate
SLOT_ALTRA_FASE = 4


def _intero(valore, nome: str, minimo: int, massimo: int | None = None) -> int:
    try:
        numero = int(str(valore).strip())
    except (TypeError, ValueError):
        raise ErroreDominio(f"❌ {nome}: inserisci un numero intero.") from None
    if numero < minimo or (massimo is not None and numero > massimo):
        limite = f"tra {minimo} e {massimo}" if massimo is not None else f"almeno {minimo}"
        raise ErroreDominio(f"❌ {nome}: il valore deve essere {limite}.")
    return numero


def stagione_valida(valore) -> str:
    """'25-26': due anni consecutivi a due cifre, come nelle righe esistenti."""
    stagione = str(valore or "").strip()
    trovata = re.fullmatch(r"(\d{2})-(\d{2})", stagione)
    if not trovata or (int(trovata.group(1)) + 1) % 100 != int(trovata.group(2)):
        raise ErroreDominio("❌ Stagione non valida: usa il formato 25-26 (due anni consecutivi).")
    return stagione


def _e_finale(fase: str) -> bool:
    return fase.lower().startswith("final")


def _e_girone(fase: str) -> bool:
    return "girone" in fase.lower()


def vista_stagione(righe: list[dict], n_squadre: int) -> dict:
    """Le righe di una stagione come griglia di posizioni da compilare.

    Una posizione per slot (1..N), anche quando e' vuota: e' quello che la
    pagina admin mostra, nello stesso ordine della pagina pubblica (finali
    prima dei gironi). Le fasi standard compaiono sempre, quelle gia'
    presenti a database con altri nomi si aggiungono. Gli slot sono almeno
    quanti servono per la posizione piu' alta registrata.
    """
    def slot(piazzamenti: dict, minimo: int) -> list[dict]:
        n = max(minimo, max(piazzamenti, default=0))
        return [{"posizione": i,
                 "squadra": piazzamenti[i]["squadra"] if i in piazzamenti else "",
                 "crediti": piazzamenti[i]["crediti_generati"] if i in piazzamenti else 0}
                for i in range(1, n + 1)]

    campionato = {r["posizione"]: r for r in righe if r["competizione"] == "Campionato"}

    per_fase: dict[str, dict] = {nome: {} for nome in FASI_COPPA_STANDARD}
    for r in righe:
        if r["competizione"] == "Coppa":
            per_fase.setdefault(r["fase"] or "", {})[r["posizione"]] = r

    coppa = []
    for nome in sorted(per_fase, key=lambda n: (not _e_finale(n), n)):
        if _e_finale(nome):
            minimo = SLOT_FASE_FINALE
        elif _e_girone(nome):
            minimo = (n_squadre + 1) // 2
        else:
            minimo = SLOT_ALTRA_FASE
        coppa.append({"nome": nome, "girone": _e_girone(nome), "slot": slot(per_fase[nome], minimo)})

    return {"campionato": slot(campionato, n_squadre), "coppa": coppa}


def _slot_da_form(form, prefisso: str):
    """(posizione, squadra, crediti) per ogni slot compilato del gruppo."""
    n = _intero(form.get(f"{prefisso}_n", "0"), "Numero di posizioni", 0, POSIZIONE_MAX)
    for posizione in range(1, n + 1):
        squadra = (form.get(f"{prefisso}_squadra_{posizione}") or "").strip()
        if not squadra:
            continue
        crediti = _intero(form.get(f"{prefisso}_crediti_{posizione}") or "0", "Crediti", 0)
        yield posizione, squadra, crediti


def piazzamenti_da_form(form, squadre_valide) -> list[dict]:
    """Legge la griglia compilata dall'admin e restituisce i piazzamenti.

    Le posizioni senza squadra sono vuote e non producono righe. Solleva
    ErroreDominio per squadre sconosciute, fasi duplicate o senza nome,
    numeri non validi, e per la stessa squadra due volte nella stessa fase
    (l'indice unico del database lo rifiuterebbe comunque, ma qui il
    messaggio dice dove).
    """
    squadre_valide = set(squadre_valide)
    righe: list[dict] = []

    def raccogli(competizione, fase, etichetta, prefisso):
        viste = set()
        for posizione, squadra, crediti in _slot_da_form(form, prefisso):
            if squadra not in squadre_valide:
                raise ErroreDominio(f"❌ Squadra non valida: {squadra}.")
            if squadra in viste:
                raise ErroreDominio(f"❌ {squadra} compare due volte in {etichetta}.")
            viste.add(squadra)
            righe.append({"competizione": competizione, "fase": fase, "squadra": squadra,
                          "posizione": posizione, "crediti_generati": crediti})

    raccogli("Campionato", None, "Campionato", "camp")

    fasi_viste = set()
    for indice in form.getlist("fase_idx"):
        prefisso = f"fase_{_intero(indice, 'Fase', 0, 50)}"
        if not any(_slot_da_form(form, prefisso)):
            continue
        fase = (form.get(f"{prefisso}_nome") or "").strip()
        if not fase:
            raise ErroreDominio("❌ Per la Coppa serve il nome della fase (es. Final 4, Girone A).")
        if len(fase) > LUNGHEZZA_FASE_MAX:
            raise ErroreDominio("❌ Nome della fase troppo lungo.")
        if fase.lower() in fasi_viste:
            raise ErroreDominio(f"❌ La fase {fase} compare due volte.")
        fasi_viste.add(fase.lower())
        raccogli("Coppa", fase, f"Coppa - {fase}", prefisso)

    return righe


def rendita_valida(valore, livello: int) -> int:
    return _intero(valore, f"Rendita del livello {livello}", 0, RENDITA_MAX)


def stadio_valido(nome, livello, livello_max: int = LIVELLO_STADIO_MAX) -> tuple[str, int]:
    nome = str(nome or "").strip()
    if not nome:
        raise ErroreDominio("❌ Il nome dello stadio non può essere vuoto.")
    if len(nome) > LUNGHEZZA_NOME_STADIO_MAX:
        raise ErroreDominio("❌ Nome dello stadio troppo lungo.")
    return nome, _intero(livello, "Livello", 0, livello_max)
