"""
Il contratto fra le pagine e i loro script.

Tre pagine - listone, movimenti di mercato e aste - disegnano ora una parte di
se' nel browser. Questa suite non esegue JavaScript, quindi quella logica non la
copre. Quello che si puo' proteggere da qui e' il contratto fra le due parti, ed
e' proprio cio' che si rompe in silenzio rinominando qualcosa:

1. gli identificatori che uno script cerca devono esistere nella sua pagina;
2. le classi che uno script mette sugli elementi devono essere definite da
   qualche foglio di stile.

Il punto 2 merita una spiegazione. `tailwind.css` e' committato gia' compilato e
nel progetto non c'e' una build che lo rigeneri: una utility non presente in quel
file semplicemente non fa nulla, e non fa nulla senza dirlo. Nei template una
classe sbagliata si nota rileggendo il markup; in una stringa dentro il
JavaScript, no.
"""

import re
from pathlib import Path

import pytest

RADICE = Path(__file__).resolve().parent.parent
JS = RADICE / "app" / "static" / "js"
TEMPLATES = RADICE / "app" / "templates"
CSS = RADICE / "app" / "static" / "css"

# Lo script di ogni pagina e la pagina che lo carica.
SCRIPT_DI_PAGINA = {
    "listone.js": "/listone",
    "movimenti_mercato.js": "/movimenti_mercato",
    "aste.js": "/aste",
}

# Usato da piu' pagine: non ha una pagina propria in cui cercare gli id.
SCRIPT_CONDIVISI = ("paginazione.js",)

# Le icone arrivano dal CDN di Bootstrap Icons, non da un foglio di stile locale.
PREFISSI_ESTERNI = ("bi", "bi-")


def _sorgente(nome):
    return (JS / nome).read_text(encoding="utf-8")


def _classi_definite():
    """Le classi note: quelle compilate, quelle dei componenti, quelle inline."""
    fogli = [(CSS / "tailwind.css").read_text(encoding="utf-8"),
             (CSS / "componenti.css").read_text(encoding="utf-8")]
    for template in TEMPLATES.glob("*.html"):
        fogli += re.findall(r"<style>(.*?)</style>", template.read_text(encoding="utf-8"), re.S)

    definite = set()
    for foglio in fogli:
        definite |= {re.sub(r"\\(.)", r"\1", c) for c in re.findall(r"\.((?:[-\w]|\\.)+)", foglio)}
    return definite


def _classi_di_aggancio(sorgente):
    """Le classi che lo script usa per ritrovare gli elementi, non per vestirli.

    `mercato-toggle` o `evento-testo` non hanno e non devono avere CSS: servono
    solo a `querySelector`. Si riconoscono dal fatto che lo script stesso le
    cerca, il che le distingue da una utility scritta male.
    """
    selettori = re.findall(r"querySelector(?:All)?\('([^']+)'\)", sorgente)
    return {c for selettore in selettori for c in re.findall(r"\.([-\w]+)", selettore)}


def _classi_usate(sorgente):
    """Le classi che lo script mette sugli elementi.

    Si guardano i punti in cui una classe puo' nascere: l'assegnazione a
    `className` (anche quando e' un ternario o una concatenazione), le chiamate
    a `classList`, e i tre costruttori di elementi usati dalle pagine.
    """
    frammenti = []
    frammenti += re.findall(r"\.className = ([^;]+);", sorgente)
    frammenti += re.findall(r"classList\.(?:add|remove|toggle)\(([^)]*)\)", sorgente)
    frammenti += re.findall(r"(?:testo|elemento)\('\w+', ('[^']*')", sorgente)
    frammenti += re.findall(r"cella\(('[^']*')", sorgente)

    usate = set()
    for frammento in frammenti:
        for stringa in re.findall(r"'([^']*)'", frammento):
            usate |= {c for c in stringa.split() if c}
    return usate


@pytest.fixture(scope="module")
def classi_definite():
    return _classi_definite()


TUTTI_GLI_SCRIPT = sorted(SCRIPT_DI_PAGINA) + list(SCRIPT_CONDIVISI)


@pytest.mark.parametrize("script", TUTTI_GLI_SCRIPT)
def test_ogni_classe_usata_dal_javascript_e_definita(script, classi_definite):
    usate = _classi_usate(_sorgente(script))
    assert usate, f"{script}: nessuna classe rilevata, l'estrazione si e' rotta"

    note = classi_definite | _classi_di_aggancio(_sorgente(script))
    mancanti = sorted(c for c in usate - note if not c.startswith(PREFISSI_ESTERNI))
    assert not mancanti, f"{script} usa classi che non esistono in nessun foglio di stile: {mancanti}"


@pytest.mark.db
@pytest.mark.parametrize("script,url", sorted(SCRIPT_DI_PAGINA.items()))
def test_ogni_identificatore_cercato_esiste_nella_pagina(script, url, client):
    html = client.get(url).get_data(as_text=True)
    cercati = set(re.findall(r"getElementById\('([^']+)'\)", _sorgente(script)))
    assert cercati, f"{script}: nessun identificatore rilevato, l'estrazione si e' rotta"

    mancanti = sorted(i for i in cercati if f'id="{i}"' not in html)
    assert not mancanti, f"{script} cerca identificatori assenti da {url}: {mancanti}"


@pytest.mark.db
@pytest.mark.parametrize("script,url", sorted(SCRIPT_DI_PAGINA.items()))
def test_ogni_pagina_carica_i_suoi_script(script, url, client):
    """Il componente di paginazione va caricato prima di chi lo usa."""
    html = client.get(url).get_data(as_text=True)

    posizione_componente = html.find("js/paginazione.js")
    posizione_script = html.find(f"js/{script}")
    assert posizione_script != -1, f"{url} non carica {script}"
    assert 0 <= posizione_componente < posizione_script, \
        f"{url} carica {script} prima di paginazione.js, che quindi non esiste ancora"
