"""
Ricostruzione del tabellone Coppa (semifinali e finale) dai piazzamenti
dell'albo d'oro. Funzione pura, nessun accesso a database.

L'albo d'oro registra solo piazzamenti finali (posizione 1, 2, 3...), non i
risultati dei singoli incontri: non c'e' una riga che dica "la semifinale 1
l'ha vinta la tal squadra". Ma con la regola fissa di accoppiamento della
Coppa non serve salvarli a parte, si ricavano dai piazzamenti che ci sono
gia':

- dai due gironi passano le prime due
- le semifinali sono incrociate: 1° Girone A - 2° Girone B, 1° Girone B - 2°
  Girone A
- la fase finale registra solo le due squadre arrivate in fondo (posizione 1
  = campione, 2 = finalista perdente)

Arrivare in finale equivale ad aver vinto la propria semifinale: incrociando
le due squadre della finale con le due semifinali si risale a chi ha vinto
quale, senza ambiguita' (una squadra non puo' comparire in entrambe).
"""


def calcola(righe_stagione: list[dict]) -> dict | None:
    """None se il tabellone non si puo' ricostruire (non esattamente due
    gironi, o la fase finale non ha campione e finalista) invece di uno a
    metà: in quel caso la pagina torna alle tabelle piatte per quella fase.
    """
    coppa = [r for r in righe_stagione if r["competizione"] == "Coppa"]

    gironi: dict[str, list[dict]] = {}
    finale: list[dict] = []
    for r in coppa:
        fase = (r["fase"] or "").strip()
        if "girone" in fase.lower():
            gironi.setdefault(fase, []).append(r)
        elif fase.lower().startswith("final"):
            finale.append(r)

    nomi_gironi = sorted(gironi.keys())
    if len(nomi_gironi) != 2:
        return None

    girone_a = sorted(gironi[nomi_gironi[0]], key=lambda r: r["posizione"])
    girone_b = sorted(gironi[nomi_gironi[1]], key=lambda r: r["posizione"])
    if len(girone_a) < 2 or len(girone_b) < 2:
        return None

    finale = sorted(finale, key=lambda r: r["posizione"])
    campione = next((r for r in finale if r["posizione"] == 1), None)
    finalista = next((r for r in finale if r["posizione"] == 2), None)
    if not campione or not finalista:
        return None

    semifinale_1 = (girone_a[0], girone_b[1])
    semifinale_2 = (girone_b[0], girone_a[1])
    nomi_finalisti = {campione["squadra"], finalista["squadra"]}

    def vincitore_di(semifinale):
        nomi = {semifinale[0]["squadra"], semifinale[1]["squadra"]}
        incrocio = nomi & nomi_finalisti
        if len(incrocio) != 1:
            return None  # dati incoerenti: meglio niente tabellone che uno sbagliato
        nome_vincitore = next(iter(incrocio))
        return semifinale[0] if semifinale[0]["squadra"] == nome_vincitore else semifinale[1]

    vincitore_sf1 = vincitore_di(semifinale_1)
    vincitore_sf2 = vincitore_di(semifinale_2)
    if not vincitore_sf1 or not vincitore_sf2:
        return None

    return {
        "semifinale_1": {"squadre": semifinale_1, "vincitore": vincitore_sf1},
        "semifinale_2": {"squadre": semifinale_2, "vincitore": vincitore_sf2},
        "finale": {"squadre": (vincitore_sf1, vincitore_sf2), "vincitore": campione},
    }
