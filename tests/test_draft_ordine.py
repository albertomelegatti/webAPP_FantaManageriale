"""Ordine di chiamata del draft: calcoli puri, senza database."""

import pytest

from app.domini.draft_ordine import (
    OrdineNonValido, numero_pick, ordine_da_classifica, stagione_della_classifica)


def _classifica(n=10):
    return [(f"S{p}", p) for p in range(1, n + 1)]


class TestStagione:
    def test_il_draft_usa_la_stagione_precedente(self):
        assert stagione_della_classifica(2026) == "25-26"
        assert stagione_della_classifica(2027) == "26-27"

    def test_cambio_di_secolo(self):
        assert stagione_della_classifica(2000) == "99-00"


class TestOrdine:
    def test_chi_chiude_ultimo_sceglie_per_primo(self):
        ordine = ordine_da_classifica(_classifica())
        assert ordine[0] == {"numero": 1, "giro": 1, "squadra": "S10"}
        assert ordine[9] == {"numero": 10, "giro": 1, "squadra": "S1"}

    def test_trenta_pick_numerate_da_1_a_30(self):
        ordine = ordine_da_classifica(_classifica())
        assert [p["numero"] for p in ordine] == list(range(1, 31))

    def test_il_giro_3_ripete_l_ordine_del_giro_1(self):
        ordine = ordine_da_classifica(_classifica())
        giro1 = [p["squadra"] for p in ordine if p["giro"] == 1]
        giro3 = [p["squadra"] for p in ordine if p["giro"] == 3]
        assert giro1 == giro3
        assert [p["numero"] for p in ordine if p["giro"] == 3] == list(range(21, 31))

    def test_numero_pick(self):
        assert numero_pick(1, 10, 10) == 1
        assert numero_pick(2, 1, 10) == 20
        assert numero_pick(3, 5, 10) == 26

    def test_ogni_squadra_ha_una_pick_per_giro(self):
        ordine = ordine_da_classifica(_classifica())
        for squadra, _ in _classifica():
            assert sorted(p["giro"] for p in ordine if p["squadra"] == squadra) == [1, 2, 3]

    def test_l_ordine_in_ingresso_non_conta(self):
        mescolata = list(reversed(_classifica()))
        assert ordine_da_classifica(mescolata) == ordine_da_classifica(_classifica())


class TestClassificaNonValida:
    def test_vuota(self):
        with pytest.raises(OrdineNonValido):
            ordine_da_classifica([])

    def test_ex_aequo(self):
        with pytest.raises(OrdineNonValido):
            ordine_da_classifica([("A", 1), ("B", 1), ("C", 3)])

    def test_buco(self):
        with pytest.raises(OrdineNonValido):
            ordine_da_classifica([("A", 1), ("B", 3)])

    def test_squadra_doppia(self):
        with pytest.raises(OrdineNonValido):
            ordine_da_classifica([("A", 1), ("A", 2)])
