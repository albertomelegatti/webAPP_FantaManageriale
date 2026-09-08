"""
Filtro "Squadra attuale" del listone.

Gli svincolati non sono una squadra vera: nel menu a tendina l'opzione va
rietichettata ("— Svincolati —") e portata subito sotto "Tutte", prima delle
squadre. Il `value` resta "Svincolato" perche' e' la chiave usata dal filtro
lato client (data-squadra).
"""

import re

import pytest

pytestmark = pytest.mark.db


def _opzioni_squadra(risposta):
    """Lista di (value, label) del select #filtro-squadra-att, in ordine."""
    corpo = risposta.get_data(as_text=True)
    blocco = re.search(
        r'<select id="filtro-squadra-att".*?</select>', corpo, re.S
    )
    assert blocco, "select del filtro squadre non trovato"
    return [
        (v, testo.strip())
        for v, testo in re.findall(r'<option value="([^"]*)">([^<]*)</option>', blocco.group(0))
    ]


class TestFiltroSquadreListone:
    def test_svincolati_rietichettati_e_subito_sotto_tutte(self, app):
        opzioni = _opzioni_squadra(app.test_client().get("/listone"))

        assert opzioni[0] == ("", "Tutte")
        assert opzioni[1] == ("Svincolato", "— Svincolati —")

    def test_nessuna_opzione_con_etichetta_svincolato_grezza(self, app):
        opzioni = _opzioni_squadra(app.test_client().get("/listone"))

        assert all(label != "Svincolato" for _, label in opzioni)
        # Il value resta invariato: e' la chiave del filtro lato client.
        assert any(value == "Svincolato" for value, _ in opzioni)

    def test_le_squadre_vere_restano_dopo_gli_svincolati(self, app):
        opzioni = _opzioni_squadra(app.test_client().get("/listone"))
        squadre_vere = [label for _, label in opzioni[2:]]

        assert squadre_vere == sorted(squadre_vere)
        assert "— Svincolati —" not in squadre_vere
