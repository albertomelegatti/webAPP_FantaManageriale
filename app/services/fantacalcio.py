"""
Sincronizzazione dell'id fantacalcio.it di ogni giocatore (per il suo
campioncino) e composizione della pagina di revisione delle corrispondenze
ambigue o non trovate. Stessa impostazione del matching Transfermarkt (vedi
app/blueprints/jobs.py, app/blueprints/admin.py), semplificata perché qui non
serve una mappa club ne' suggerimenti fuzzy: il nome del giocatore in questa
app arriva già dal listone di fantacalcio.it.
"""

from app.core import fantacalcio_api
from app.core.errori import ErroreDominio
from app.domini.matching_fantacalcio import candidati_esatti
from app.domini.ruoli import pulisci_ruolo
from app.repositories import fantacalcio as fantacalcio_repo

# Sotto questa soglia il dump scaricato e' sospetto (pagina cambiata, errore
# di rete parziale): meglio abortire senza scrivere nulla che svuotare la
# cache con un risultato inutilizzabile. La pagina ne ha oggi circa 600.
SOGLIA_MINIMA_GIOCATORI = 400


def sincronizza(cur) -> dict:
    """Scarica il listone, aggiorna la cache e prova ad abbinare ogni
    giocatore di prima fascia non ancora abbinato. Ritorna un riepilogo
    {auto, ambigui, non_trovati}. Non committa: il chiamante decide quando.
    """
    giocatori_fc = fantacalcio_api.scarica_quotazioni()
    if len(giocatori_fc) < SOGLIA_MINIMA_GIOCATORI:
        raise ErroreDominio(
            f"❌ Scaricati solo {len(giocatori_fc)} giocatori da fantacalcio.it "
            f"(attesi almeno {SOGLIA_MINIMA_GIOCATORI}): pagina forse cambiata, "
            "sincronizzazione annullata senza scrivere nulla."
        )

    fantacalcio_repo.svuota_cache(cur)
    for g in giocatori_fc:
        fantacalcio_repo.inserisci_in_cache(cur, g)

    riepilogo = {"auto": 0, "ambigui": 0, "non_trovati": 0}
    for giocatore in fantacalcio_repo.non_ancora_mappati(cur):
        candidati = candidati_esatti(giocatore["nome"], giocatori_fc)
        if len(candidati) == 1:
            fantacalcio_repo.assegna_abbinamento(cur, giocatore["id"], candidati[0]["id_fantacalcio"])
            riepilogo["auto"] += 1
        elif len(candidati) > 1:
            fantacalcio_repo.segnala_candidati_ambigui(
                cur, giocatore["id"], [c["id_fantacalcio"] for c in candidati])
            riepilogo["ambigui"] += 1
        else:
            fantacalcio_repo.segnala_non_trovato(cur, giocatore["id"])
            riepilogo["non_trovati"] += 1

    return riepilogo


def dati_revisione(cur) -> list[dict]:
    """I giocatori con candidati ambigui o non trovati, con il resto del
    listone fantacalcio.it disponibile per una ricerca manuale sui "non
    trovati" (niente suggerimenti automatici: qui basta il match esatto)."""
    righe = fantacalcio_repo.da_rivedere(cur)

    per_giocatore = {}
    for r in righe:
        entry = per_giocatore.setdefault(r["id_giocatore"], {
            "id": r["id_giocatore"],
            "nome": r["nome"],
            "club": r["club"],
            "ruolo": pulisci_ruolo(r["ruolo"]),
            "candidati": [],
        })
        if r["id_fantacalcio"] is not None:
            entry["candidati"].append({"id_fantacalcio": r["id_fantacalcio"], "nome_fc": r["nome_fc"], "squadra_fc": r["squadra_fc"]})

    tutti = fantacalcio_repo.tutti_in_cache(cur)

    for g in per_giocatore.values():
        g["categoria"] = "ambiguo" if g["candidati"] else "non_trovato"
        g["ricerca"] = [] if g["candidati"] else tutti

    ordine_categoria = {"ambiguo": 0, "non_trovato": 1}
    return sorted(per_giocatore.values(), key=lambda g: (ordine_categoria[g["categoria"]], g["nome"]))
