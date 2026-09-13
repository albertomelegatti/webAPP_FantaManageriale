"""
Il listone e le righe disegnate dal browser.

La pagina mandava l'HTML di oltre cinquecento righe, ognuna con un attributo
JSON che ripeteva i nomi dei tredici campi della scheda di dettaglio. Ora manda
solo i dati, in forma compatta, e le righe le disegna static/js/listone.js.

Il grosso della logica si e' quindi spostato nel JavaScript, che questa suite non
esegue. Quello che si puo' proteggere da qui e' il *contratto* fra le due parti:
i campi che il servizio spedisce, gli identificatori che il JavaScript cerca nel
template, e le due mappe di colori e icone duplicate dalle macro Jinja. Sono
proprio le cose che si rompono in silenzio rinominando qualcosa.
"""

import json
import re
from datetime import date
from pathlib import Path

import pytest

JS_LISTONE = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "listone.js"
MACROS = Path(__file__).resolve().parent.parent / "app" / "templates" / "_macros.html"
TEMPLATE = Path(__file__).resolve().parent.parent / "app" / "templates" / "listone.html"
CSS = Path(__file__).resolve().parent.parent / "app" / "static" / "css" / "tailwind.css"


@pytest.fixture(scope="module")
def sorgente_js():
    return JS_LISTONE.read_text(encoding="utf-8")


def _blocco_dati(html):
    return json.loads(re.search(r'id="datiGiocatori">(.*?)</script>', html, re.S).group(1))


@pytest.mark.db
class TestDatiCompatti:
    def test_i_nomi_dei_campi_viaggiano_una_volta_sola(self, cur):
        from app.services import listone as servizio
        dati = servizio.dati_pagina(cur)["dati_giocatori"]

        assert dati["campi"] == list(servizio.CAMPI)
        assert all(len(riga) == len(dati["campi"]) for riga in dati["righe"])

    def test_c_e_una_riga_per_giocatore(self, cur):
        from app.services import listone as servizio
        dati = servizio.dati_pagina(cur)

        assert len(dati["dati_giocatori"]["righe"]) == dati["totale_giocatori"]
        assert dati["totale_giocatori"] > 0, "il listone del database di sviluppo e' vuoto"

    def test_ogni_logo_mostrato_ha_la_sua_versione(self, client):
        """Senza il `?v=` giusto un logo cambiato resterebbe quello in cache."""
        html = client.get("/listone").get_data(as_text=True)
        versioni = json.loads(re.search(r"data-loghi-versioni='(.*?)'", html, re.S).group(1))
        dati = _blocco_dati(html)

        colonna = {campo: i for i, campo in enumerate(dati["campi"])}
        usati = {
            riga[colonna[campo]]
            for riga in dati["righe"]
            for campo in ("squadra_username", "detentore_username")
            if riga[colonna[campo]]
        }
        assert usati <= set(versioni), f"loghi senza versione: {sorted(usati - set(versioni))}"
        assert "svincolato" in versioni


@pytest.mark.db
class TestPaginaAlleggerita:
    def test_il_server_non_manda_piu_le_righe(self, client):
        html = client.get("/listone").get_data(as_text=True)
        corpo = re.search(r'id="listoneBody">(.*?)</tbody>', html, re.S).group(1)

        assert corpo.strip() == "", "le righe sono tornate nell'HTML del server"
        assert "data-info" not in html, "i dati sono tornati negli attributi di riga"

    def test_i_dati_arrivano_tutti_nel_blocco_json(self, client):
        html = client.get("/listone").get_data(as_text=True)
        dati = _blocco_dati(html)

        conteggio = re.search(r'id="risultati-count">(\d+)<', html).group(1)
        assert len(dati["righe"]) == int(conteggio)


class TestContrattoConIlJavascript:
    """Cio' che il JavaScript si aspetta dal server deve esistere davvero."""

    # Nomi che il JavaScript calcola da se' dopo aver letto i dati.
    CAMPI_DERIVATI = {"nomeCercabile", "ruoli"}

    def test_legge_solo_campi_che_il_servizio_spedisce(self, sorgente_js):
        from app.services.listone import CAMPI

        letti = set(re.findall(r"\bg\.([a-zA-Z_][a-zA-Z0-9_]*)", sorgente_js))
        assert letti - self.CAMPI_DERIVATI <= set(CAMPI), \
            f"campi letti dal JavaScript ma non spediti: {sorted(letti - self.CAMPI_DERIVATI - set(CAMPI))}"

    @pytest.mark.db
    def test_trova_nel_template_tutti_gli_elementi_che_cerca(self, client, sorgente_js):
        html = client.get("/listone").get_data(as_text=True)

        cercati = set(re.findall(r"getElementById\('([^']+)'\)", sorgente_js))
        mancanti = [i for i in cercati if f'id="{i}"' not in html]
        assert not mancanti, f"identificatori cercati dal JavaScript ma assenti dalla pagina: {mancanti}"

    def test_i_colori_dei_ruoli_non_divergono_dalle_macro(self, sorgente_js):
        """Le stesse coppie ruolo/colore stanno in due posti: devono coincidere."""
        nel_js = dict(re.findall(r"(\w+): '(#[0-9a-f]{6})'",
                                 re.search(r"COLORI_RUOLO = \{(.*?)\};", sorgente_js, re.S).group(1)))
        macro = MACROS.read_text(encoding="utf-8")
        nelle_macro = dict(re.findall(r"'(\w+)': '(#[0-9a-f]{6})'",
                                      re.search(r"set colori = \{(.*?)\}", macro, re.S).group(1)))

        assert nel_js == nelle_macro

    def test_le_icone_dei_contratti_non_divergono_dalle_macro(self, sorgente_js):
        nel_js = dict(re.findall(r"'([^']+)': '(bi-[\w-]+)'",
                                 re.search(r"ICONE_CONTRATTO = \{(.*?)\};", sorgente_js, re.S).group(1)))
        macro = MACROS.read_text(encoding="utf-8")
        nelle_macro = dict(re.findall(r"'([^']+)': '(bi-[\w-]+)'",
                                      re.search(r"set icone = \{(.*?)\}", macro, re.S).group(1)))

        assert nel_js == nelle_macro


class TestClassiEsistenti:
    """Le classi che il JavaScript mette sulle righe devono esistere davvero.

    `tailwind.css` e' committato gia' compilato e nel repository non c'e' una
    build che lo rigeneri: una utility non presente nel file non fa nulla, e
    siccome non fa nulla *in silenzio* non se ne accorge nessuno. Qui si
    controllano le classi generate dal JavaScript, che nessun occhio incrocia
    leggendo il template.
    """

    # Le icone arrivano dal CDN di Bootstrap Icons, non da tailwind.css.
    CLASSI_ESTERNE = {"bi"}

    @staticmethod
    def _classi_compilate():
        css = CSS.read_text(encoding="utf-8")
        return {re.sub(r"\\(.)", r"\1", c) for c in re.findall(r"\.((?:[-\w]|\\.)+)", css)}

    @staticmethod
    def _classi_della_pagina():
        """Le classi definite dal foglio di stile interno al template."""
        stile = re.search(r"<style>(.*?)</style>", TEMPLATE.read_text(encoding="utf-8"), re.S).group(1)
        return set(re.findall(r"\.([-\w]+)", stile))

    def test_ogni_classe_usata_dal_javascript_e_definita(self, sorgente_js):
        # Le stringhe di classi nel JavaScript sono quelle passate a `testo()`,
        # assegnate a `.className` o costruite per le righe della tabella.
        stringhe = re.findall(r"className = '([^']*)'|testo\('\w+', '([^']*)'", sorgente_js)
        stringhe += [(s, "") for s in re.findall(r"cella\('([^']*)'", sorgente_js)]

        usate = {c for coppia in stringhe for s in coppia for c in s.split() if c}
        definite = self._classi_compilate() | self._classi_della_pagina() | self.CLASSI_ESTERNE

        assert usate <= definite, f"classi che non esistono in nessun foglio di stile: {sorted(usate - definite)}"


class TestStatoU21:
    def test_senza_soglia_non_e_determinabile(self):
        from app.services.listone import stato_u21
        assert stato_u21(date(2010, 1, 1), None) == ""

    def test_senza_data_di_nascita_non_e_determinabile(self):
        from app.services.listone import stato_u21
        assert stato_u21(None, 2005) == ""

    def test_la_soglia_e_inclusiva(self):
        """Nato nell'anno di soglia: e' U21, stessa regola delle aste."""
        from app.services.listone import stato_u21
        assert stato_u21(date(2005, 6, 1), 2005) == "si"
        assert stato_u21(date(2004, 12, 31), 2005) == "no"
