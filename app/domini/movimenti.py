"""Riconoscimento delle squadre citate in un testo libero."""


def squadre_citate(testo: str, nomi_squadre: list[str]) -> list[str]:
    """Le squadre il cui nome compare come sottostringa nel testo.

    Serve solo per la comunicazione manuale dell'admin (testo libero, senza una
    squadra strutturata a monte): e' la stessa euristica per sottostringa che
    prima cercava il legame movimento-squadra a ogni lettura, applicata qui una
    volta sola in scrittura. Per tutti gli altri eventi - generati dal codice,
    non digitati a mano - le squadre sono note con certezza e non passano di qui.
    """
    testo_minuscolo = testo.lower()
    return [nome for nome in nomi_squadre if nome.lower() in testo_minuscolo]
