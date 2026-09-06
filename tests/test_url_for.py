"""
Guardia sugli endpoint referenziati da url_for.

Nasce da un 500 in produzione: la Fase 2 ha spostato le route nei blueprint e
rinominato gli endpoint, ma la sostituzione automatica cercava `url_for('home')`
con gli apici singoli e ha lasciato indietro un `url_for("home")` con i doppi.
L'errore non compare all'import ne' all'avvio: esplode solo quando quella
specifica riga viene eseguita.

Gli smoke test non l'avevano intercettato perche' usano un client autenticato,
mentre la riga rotta sta nel ramo per gli utenti anonimi.

Questo test attraversa tutto il codice e tutti i template e verifica che ogni
endpoint citato esista davvero, senza bisogno di percorrere la route.
"""

import glob
import re

import pytest

RE_URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z0-9_.]+)['"]""")


def _riferimenti():
    for percorso in (glob.glob("app/**/*.py", recursive=True)
                     + glob.glob("app/templates/**/*.html", recursive=True)):
        with open(percorso, encoding="utf-8") as f:
            for numero, riga in enumerate(f, 1):
                for m in RE_URL_FOR.finditer(riga):
                    yield percorso, numero, m.group(1)


@pytest.mark.db
def test_ogni_url_for_punta_a_un_endpoint_esistente(app):
    validi = {r.endpoint for r in app.url_map.iter_rules()}
    rotti = [f"{p}:{n} -> url_for('{e}')"
             for p, n, e in _riferimenti() if e not in validi]
    assert not rotti, "Endpoint inesistenti:\n  " + "\n  ".join(rotti)


@pytest.mark.db
def test_il_controllo_esamina_davvero_qualcosa(app):
    """Sentinella: se la ricerca smettesse di trovare riferimenti, il test
    sopra passerebbe sempre senza verificare nulla."""
    assert len(list(_riferimenti())) > 50
