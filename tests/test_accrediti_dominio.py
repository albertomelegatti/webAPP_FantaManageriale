"""Accrediti annuali: stagione, chiavi del registro e somma dei premi. Calcoli puri."""

from datetime import date

import pytest

from app.domini.accrediti import (
    chiave_albo_oro, chiave_rendite_stadi, crediti_per_squadra, stagione_corrente)


class TestStagioneCorrente:
    def test_dal_2_luglio_e_la_stagione_che_inizia(self):
        assert stagione_corrente(date(2026, 7, 2)) == "26-27"
        assert stagione_corrente(date(2026, 11, 11)) == "26-27"
        assert stagione_corrente(date(2026, 12, 31)) == "26-27"

    def test_fino_all_1_luglio_e_ancora_quella_dell_anno_prima(self):
        assert stagione_corrente(date(2027, 1, 1)) == "26-27"
        assert stagione_corrente(date(2027, 7, 1)) == "26-27"
        assert stagione_corrente(date(2027, 7, 2)) == "27-28"

    def test_cambio_di_secolo(self):
        assert stagione_corrente(date(2099, 9, 1)) == "99-00"

    def test_come_telegram_get_stagione(self):
        # Stessa regola di telegram_utils.get_stagione(): le due stagioni non devono divergere.
        from unittest.mock import patch
        from app import telegram_utils
        for giorno in (date(2026, 7, 1), date(2026, 7, 2), date(2027, 3, 15)):
            with patch.object(telegram_utils, "datetime") as finto:
                finto.now.return_value = __import__("datetime").datetime(giorno.year, giorno.month, giorno.day)
                assert telegram_utils.get_stagione() == stagione_corrente(giorno)


class TestChiavi:
    def test_chiavi_distinte_per_competizione_e_tipo(self):
        assert chiave_albo_oro("25-26", "Campionato") == "albo_oro:25-26:Campionato"
        assert chiave_albo_oro("25-26", "Coppa") != chiave_albo_oro("25-26", "Campionato")
        assert chiave_rendite_stadi("26-27") == "rendite_stadi:26-27"


def _r(competizione, squadra, crediti, fase=None, posizione=1):
    return {"competizione": competizione, "fase": fase, "squadra": squadra,
            "posizione": posizione, "crediti_generati": crediti}


class TestCreditiPerSquadra:
    def test_somma_i_premi_di_una_squadra_nella_stessa_competizione(self):
        # La Coppa ha gironi e finali: una squadra puo' comparire piu' volte.
        righe = [_r("Coppa", "A", 10, "Girone A"), _r("Coppa", "A", 30, "Final 4"),
                 _r("Coppa", "B", 5, "Girone B")]
        assert crediti_per_squadra(righe, "Coppa") == [("A", 40), ("B", 5)]

    def test_considera_solo_la_competizione_richiesta(self):
        righe = [_r("Campionato", "A", 100), _r("Coppa", "A", 10)]
        assert crediti_per_squadra(righe, "Campionato") == [("A", 100)]
        assert crediti_per_squadra(righe, "Coppa") == [("A", 10)]

    def test_chi_totalizza_zero_non_compare(self):
        righe = [_r("Campionato", "A", 0), _r("Campionato", "B", 20)]
        assert crediti_per_squadra(righe, "Campionato") == [("B", 20)]

    def test_ordine_dal_premio_piu_alto_poi_per_nome(self):
        righe = [_r("Campionato", "C", 10), _r("Campionato", "B", 10), _r("Campionato", "A", 50)]
        assert crediti_per_squadra(righe, "Campionato") == [("A", 50), ("B", 10), ("C", 10)]

    def test_posizioni_senza_squadra_si_ignorano(self):
        assert crediti_per_squadra([_r("Campionato", "", 99), _r("Campionato", None, 99)], "Campionato") == []

    def test_crediti_nulli(self):
        assert crediti_per_squadra([_r("Campionato", "A", None)], "Campionato") == []

    def test_nessuna_riga(self):
        assert crediti_per_squadra([], "Campionato") == []


class TestMessaggioTelegram:
    def test_una_riga_per_squadra(self):
        from app.telegram_utils import _righe_accrediti
        testo = _righe_accrediti([("Alfa", 100), ("Beta", 5)])
        assert testo.splitlines() == ["• Alfa: +100 crediti", "• Beta: +5 crediti"]

    def test_singolare_per_un_solo_credito(self):
        from app.telegram_utils import _righe_accrediti
        assert _righe_accrediti([("Alfa", 1)]) == "• Alfa: +1 credito"
