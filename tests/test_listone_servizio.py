"""
Composizione del listone.

Ogni riga portava un attributo JSON con i tredici campi della scheda di
dettaglio, aperta solo al clic: i dati viaggiavano per tutti i cinquecento
giocatori, e con essi i nomi dei campi ripetuti ogni volta.
"""

import json
import re

import pytest

pytestmark = pytest.mark.db


class TestDatiScheda:
    def test_i_nomi_dei_campi_viaggiano_una_volta_sola(self, cur):
        from app.services import listone as servizio
        dati = servizio.dati_pagina(cur)["dati_scheda"]
        assert isinstance(dati["campi"], list)
        assert all(isinstance(r, list) for r in dati["righe"])
        assert all(len(r) == len(dati["campi"]) for r in dati["righe"])

    def test_c_e_una_riga_per_giocatore(self, cur):
        from app.services import listone as servizio
        dati = servizio.dati_pagina(cur)
        assert len(dati["dati_scheda"]["righe"]) == len(dati["giocatori"])

    def test_i_valori_corrispondono_al_giocatore(self, cur):
        from app.services import listone as servizio
        dati = servizio.dati_pagina(cur)
        campi = dati["dati_scheda"]["campi"]
        for giocatore, valori in list(zip(dati["giocatori"], dati["dati_scheda"]["righe"]))[:20]:
            scheda = dict(zip(campi, valori))
            assert scheda["nome"] == giocatore["nome"]
            assert scheda["quotazione"] == giocatore["quotazione"]
            # nella scheda il detentore del cartellino si chiama solo "detentore"
            assert scheda["detentore"] == giocatore["detentore_cartellino"]

    def test_la_pagina_non_porta_piu_i_dati_riga_per_riga(self, client):
        html = client.get("/listone").get_data(as_text=True)
        assert "data-info" not in html, "i dati sono tornati negli attributi di riga"
        assert 'id="datiGiocatori"' in html

    def test_il_blocco_json_e_valido_e_indicizzato_dalle_righe(self, client):
        html = client.get("/listone").get_data(as_text=True)
        dati = json.loads(re.search(r'id="datiGiocatori">(.*?)</script>', html, re.S).group(1))
        indici = [int(i) for i in re.findall(r'data-idx="(\d+)"', html)]
        assert indici == list(range(len(dati["righe"]))), \
            "gli indici delle righe devono corrispondere alle posizioni nel blocco"


class TestStatoU21:
    def test_senza_soglia_non_e_determinabile(self):
        from app.services.listone import stato_u21
        from datetime import date
        assert stato_u21(date(2010, 1, 1), None) == ""

    def test_senza_data_di_nascita_non_e_determinabile(self):
        from app.services.listone import stato_u21
        assert stato_u21(None, 2005) == ""

    def test_la_soglia_e_inclusiva(self):
        """Nato nell'anno di soglia: e' U21, stessa regola delle aste."""
        from app.services.listone import stato_u21
        from datetime import date
        assert stato_u21(date(2005, 6, 1), 2005) == "si"
        assert stato_u21(date(2004, 12, 31), 2005) == "no"
