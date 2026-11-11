"""Ordine di chiamata del draft, ricavato dalla classifica di campionato.

Regole (verificate sui draft gia' registrati):

- chi ha chiuso ultimo sceglie per primo: la classifica va letta al contrario;
- i giri sono tre e l'ordine NON si inverte (non e' un "serpentina"): il giro 3
  ripete l'ordine del giro 1;
- `numero` e' progressivo sull'intero draft: giro 1 = 1..N, giro 2 = N+1..2N, ...
  Con 10 squadre sono 30 pick.

Qui non c'e' niente che tocchi il database: sono solo calcoli, cosi' si provano
senza connessione.
"""

GIRI = 3


class OrdineNonValido(ValueError):
    """La classifica non permette di generare l'ordine."""


def stagione_della_classifica(anno_draft: int) -> str:
    """Il draft dell'anno N si ordina con la classifica della stagione (N-1)-N.

    Esempio: draft 2026 -> "25-26", draft 2000 -> "99-00". E' il formato di
    `albo_oro.stagione`.
    """
    return f"{(anno_draft - 1) % 100:02d}-{anno_draft % 100:02d}"


def numero_pick(giro: int, posizione: int, n_squadre: int) -> int:
    """Numero progressivo della pick di chi e' arrivato in `posizione`."""
    return (giro - 1) * n_squadre + (n_squadre + 1 - posizione)


def ordine_da_classifica(classifica, giri: int = GIRI) -> list[dict]:
    """[{numero, giro, squadra}] in ordine di chiamata.

    `classifica` e' un elenco di (squadra, posizione) con posizioni 1..N senza
    buchi ne' doppioni: un ex aequo o una squadra mancante darebbero numeri
    duplicati o pick senza proprietario, quindi si ferma prima di scrivere.
    """
    classifica = list(classifica)
    n = len(classifica)
    if n == 0:
        raise OrdineNonValido("la classifica e' vuota")

    posizioni = sorted(p for _, p in classifica)
    if posizioni != list(range(1, n + 1)):
        raise OrdineNonValido(
            f"le posizioni devono essere 1..{n} senza buchi ne' ex aequo, "
            f"trovate: {posizioni}")
    squadre = [s for s, _ in classifica]
    if len(set(squadre)) != n:
        raise OrdineNonValido("una squadra compare due volte in classifica")

    ordine = [
        {"numero": numero_pick(giro, posizione, n), "giro": giro, "squadra": squadra}
        for giro in range(1, giri + 1)
        for squadra, posizione in classifica
    ]
    return sorted(ordine, key=lambda p: p["numero"])
