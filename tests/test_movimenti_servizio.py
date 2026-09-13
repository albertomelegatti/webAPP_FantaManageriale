"""
I movimenti di mercato e le righe disegnate dal browser.

La pagina mandava l'HTML di seicento righe con il testo integrale di ogni
movimento - mezzo megabyte - per poi nasconderne la maggior parte al primo
filtro. Ora manda solo i dati, in forma compatta, e le righe le disegna
static/js/movimenti_mercato.js.

I controlli sul contratto fra pagina e script stanno in
tests/test_contratto_javascript.py, che vale per tutte e tre le pagine.
"""

import json
import re

import pytest


def _blocco_dati(html):
    return json.loads(re.search(r'id="datiMovimenti">(.*?)</script>', html, re.S).group(1))


@pytest.mark.db
class TestDatiCompatti:
    def test_i_nomi_dei_campi_viaggiano_una_volta_sola(self, cur):
        from app.services import movimenti as servizio
        dati = servizio.dati_pagina(cur)["dati_movimenti"]

        assert dati["campi"] == list(servizio.CAMPI)
        assert all(len(riga) == len(dati["campi"]) for riga in dati["righe"])
        assert dati["righe"], "il registro dei movimenti del database di sviluppo e' vuoto"

    def test_la_data_viaggia_come_la_stampava_il_template(self, cur):
        """Era `{{ m.data }}`, cioe' `str(data)`: deve apparire identica."""
        from app.services import movimenti as servizio
        from app.repositories import movimenti as movimenti_repo

        attese = [str(m["data"]) for m in movimenti_repo.tutti(cur)]
        dati = servizio.dati_pagina(cur)["dati_movimenti"]
        colonna = dati["campi"].index("data")

        assert [riga[colonna] for riga in dati["righe"]] == attese

    def test_le_stagioni_sono_dalla_piu_recente(self, cur):
        """Le costruiva il browser leggendo le righe, ora le manda il server."""
        from app.services import movimenti as servizio
        dati = servizio.dati_pagina(cur)

        stagioni = dati["stagioni_disponibili"]
        assert stagioni == sorted(stagioni, reverse=True)

        colonna = dati["dati_movimenti"]["campi"].index("stagione")
        presenti = {riga[colonna] for riga in dati["dati_movimenti"]["righe"] if riga[colonna]}
        assert set(stagioni) == presenti

    def test_le_squadre_non_comprendono_svincolato(self, cur):
        """'Svincolato' e' una riga di `squadra` ma non e' una squadra."""
        from app.services import movimenti as servizio
        assert "Svincolato" not in servizio.dati_pagina(cur)["squadre"]


@pytest.mark.db
class TestPaginaAlleggerita:
    def test_il_server_non_manda_piu_le_righe(self, client):
        html = client.get("/movimenti_mercato").get_data(as_text=True)
        corpo = re.search(r'id="mercatoBody">(.*?)</div>', html, re.S).group(1)

        assert corpo.strip() == "", "le righe sono tornate nell'HTML del server"
        assert "data-stagione=" not in html, "i dati sono tornati negli attributi di riga"

    def test_i_dati_arrivano_tutti_nel_blocco_json(self, client, cur):
        from app.repositories import movimenti as movimenti_repo

        html = client.get("/movimenti_mercato").get_data(as_text=True)
        assert len(_blocco_dati(html)["righe"]) == len(movimenti_repo.tutti(cur))

    def test_la_pagina_e_molto_piu_leggera_dei_suoi_dati(self, client):
        """Il guadagno sta nel non mandare l'HTML di ogni riga.

        La soglia e' larga apposta: serve a intercettare un ritorno all'HTML
        riga per riga, non a fissare una dimensione.
        """
        html = client.get("/movimenti_mercato").get_data(as_text=True)
        righe = len(_blocco_dati(html)["righe"])

        assert len(html) < righe * 400, \
            f"{len(html)} byte per {righe} movimenti: la pagina sta rimandando il markup"
