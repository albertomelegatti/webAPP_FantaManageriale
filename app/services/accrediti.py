"""Accrediti annuali: premi delle competizioni (albo d'oro) e rendite degli stadi.

Un accredito somma crediti alle squadre e va fatto UNA volta per stagione. La
garanzia e' il registro: l'accredito scrive prima la sua riga (chiave unica) e
poi somma i crediti, nella stessa transazione del chiamante. Se la riga c'e' gia'
si ferma senza toccare niente; se qualcosa va storto dopo, l'annullamento della
transazione toglie anche la riga, quindi un accredito fallito si puo' ripetere.

Le funzioni non fanno commit: lo fa la route, che poi manda Telegram.
Il registro deve esistere: senza la tabella non si accredita (nessuna guardia).
"""

from app.core.errori import ErroreDominio
from app.domini import accrediti as dominio
from app.repositories import accrediti as registro_repo
from app.repositories import albo_oro as albo_oro_repo
from app.repositories import squadre as squadre_repo
from app.services.crediti_stadi_slot import rendite_da_accreditare, rendite_in_uso

MANCA_REGISTRO = ("❌ Registro degli accrediti non ancora creato: lancia "
                  "CronJob/accrediti_annuali_schema.sql prima di accreditare.")


class GiaAccreditato(ErroreDominio):
    pass


def _applica(cur, chiave, tipo, stagione, competizione, da, accrediti):
    """Registra e somma. `accrediti` e' [(squadra, crediti)]; vuoto = niente da fare."""
    if not registro_repo.disponibile(cur):
        raise ErroreDominio(MANCA_REGISTRO)
    if not accrediti:
        raise ErroreDominio("❌ Non c'è nessun credito da accreditare.")

    totale = sum(c for _, c in accrediti)
    if not registro_repo.registra(cur, chiave, tipo, stagione, competizione, da, len(accrediti), totale):
        esistente = registro_repo.leggi(cur, chiave)
        quando = esistente["eseguito_il"].strftime("%d/%m/%Y") if esistente else "?"
        raise GiaAccreditato(f"⚠️ Già accreditato il {quando}: non si ripete nella stessa stagione.")

    for squadra, crediti in accrediti:
        squadre_repo.aggiungi_crediti(cur, squadra, crediti)
    return {"accrediti": accrediti, "totale": totale}


# --- Premi delle competizioni (albo d'oro) --------------------------------------

def stato_albo(cur, stagione: str) -> dict:
    """Per ogni competizione della stagione: cosa si accrediterebbe e se e' gia' stato fatto."""
    righe = albo_oro_repo.per_stagione(cur, stagione)
    registro_ok = registro_repo.disponibile(cur)
    competizioni = []
    for competizione in dominio.COMPETIZIONI:
        accrediti = dominio.crediti_per_squadra(righe, competizione)
        competizioni.append({
            "competizione": competizione,
            "accrediti": accrediti,
            "totale": sum(c for _, c in accrediti),
            "registro": (registro_repo.leggi(cur, dominio.chiave_albo_oro(stagione, competizione))
                         if registro_ok else None),
        })
    return {"registro_ok": registro_ok, "competizioni": competizioni}


def accredita_albo(cur, stagione: str, competizione: str, da: str) -> dict:
    if competizione not in dominio.COMPETIZIONI:
        raise ErroreDominio("❌ Competizione non valida.")
    accrediti = dominio.crediti_per_squadra(albo_oro_repo.per_stagione(cur, stagione), competizione)
    return _applica(cur, dominio.chiave_albo_oro(stagione, competizione), "albo_oro",
                    stagione, competizione, da, accrediti)


# --- Rendite degli stadi --------------------------------------------------------

def stato_rendite(cur, stagione: str) -> dict:
    registro_ok = registro_repo.disponibile(cur)
    return {"registro_ok": registro_ok,
            "registro": (registro_repo.leggi(cur, dominio.chiave_rendite_stadi(stagione))
                         if registro_ok else None)}


def accredita_rendite(cur, stagione: str, da: str) -> dict:
    """Usa le rendite salvate, non quelle digitate e non ancora salvate nel form."""
    accrediti = rendite_da_accreditare(squadre_repo.tutte_con_stadio(cur), rendite_in_uso(cur))
    return _applica(cur, dominio.chiave_rendite_stadi(stagione), "rendite_stadi",
                    stagione, None, da, accrediti)
