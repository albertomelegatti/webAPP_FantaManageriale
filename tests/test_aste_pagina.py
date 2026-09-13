"""
Paginazione delle aste concluse.

A differenza del listone e dei movimenti, qui il server continua a disegnare le
schede: la pagina pesa pochi kilobyte compressi e non c'e' niente da
alleggerire. Il problema e' solo la lunghezza dell'elenco, che cresce di
stagione in stagione, e static/js/aste.js si limita a mostrarne una parte alla
volta riordinando gli elementi gia' presenti.

Non c'e' quindi markup duplicato in JavaScript: quello che questa suite deve
proteggere e' l'aggancio fra template e script, cioe' il marcatore sulle schede
e il contenitore che le raccoglie.
"""

import re

import pytest

pytestmark = pytest.mark.db


def _sezione_concluse(html):
    """Il contenitore delle aste concluse, da cui lo script prende le schede."""
    trovato = re.search(r'id="asteConcluse">(.*?)\n        </div>', html, re.S)
    assert trovato, "il contenitore delle aste concluse non c'e' piu'"
    return trovato.group(1)


class TestAgganciDelloScript:
    def test_ogni_asta_conclusa_porta_il_marcatore(self, client, cur):
        """Senza la classe lo script non troverebbe le schede da impaginare."""
        cur.execute("SELECT COUNT(*) AS n FROM asta WHERE stato = 'conclusa';")
        attese = cur.fetchone()["n"]

        html = client.get("/aste").get_data(as_text=True)
        assert html.count('class="asta-conclusa ') == attese

    def test_la_barra_di_paginazione_e_nella_sezione_delle_concluse(self, client):
        """Le altre due sezioni restano intere: sono poche aste per natura."""
        html = client.get("/aste").get_data(as_text=True)

        assert html.count('id="paginazione"') == 1
        assert html.index('id="asteConcluse"') < html.index('id="paginazione"')

    def test_le_altre_sezioni_non_hanno_marcatori(self, client):
        """Il marcatore deve stare solo sulle concluse, o si impaginerebbe tutto."""
        html = client.get("/aste").get_data(as_text=True)
        prima_delle_concluse = html[:html.index('id="asteConcluse"')]

        assert "asta-conclusa" not in prima_delle_concluse
