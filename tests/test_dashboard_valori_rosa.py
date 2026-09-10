"""
Valore di mercato della rosa nella dashboard: funzione pura, nessun database.

Il totale in testata somma i giocatori di cui la squadra detiene il cartellino,
prestiti reali esclusi. I sottototali seguono i quattro elenchi della pagina
cosi' come sono mostrati, quindi non sommano per forza al totale.
"""

from app.services.dashboard import _valore_di_mercato, _valori_rosa

SQUADRA = "Real Fanta"


def _g(tipo_contratto, valore_mercato, *, squadra_att=SQUADRA, detentore=SQUADRA):
    return {
        "squadra_att": squadra_att,
        "detentore_cartellino": detentore,
        "tipo_contratto": tipo_contratto,
        "valore_mercato": valore_mercato,
    }


class TestValoreDiMercato:
    def test_somma_i_valori_noti_e_li_formatta_in_milioni(self):
        assert _valore_di_mercato([_g("Hold", 40_000_000), _g("Hold", 35_000_000)]) == "75 Mln"

    def test_arrotonda_al_milione_piu_vicino(self):
        assert _valore_di_mercato([_g("Hold", 40_400_000), _g("Hold", 35_300_000)]) == "76 Mln"
        assert _valore_di_mercato([_g("Hold", 1_800_000)]) == "2 Mln"

    def test_ignora_i_giocatori_senza_valore_sincronizzato(self):
        assert _valore_di_mercato([_g("Hold", 10_000_000), _g("Hold", None)]) == "10 Mln"

    def test_none_quando_nessun_valore_e_sincronizzato(self):
        assert _valore_di_mercato([_g("Hold", None), _g("Hold", None)]) is None

    def test_none_su_elenco_vuoto(self):
        assert _valore_di_mercato([]) is None


class TestTotaleDellaRosa:
    def test_somma_solo_i_giocatori_col_cartellino_della_squadra(self):
        giocatori = [
            _g("Hold", 20_000_000),
            _g("Indeterminato", 30_000_000),
            # cartellino di un'altra squadra: preso in prestito, non conta
            _g("Fanta-Prestito", 50_000_000, detentore="Altra"),
        ]
        assert _valori_rosa(giocatori, SQUADRA)["valore_rosa_totale"] == "50 Mln"

    def test_include_la_primavera(self):
        giocatori = [_g("Hold", 10_000_000), _g("Primavera", 5_000_000)]
        assert _valori_rosa(giocatori, SQUADRA)["valore_rosa_totale"] == "15 Mln"

    def test_esclude_il_prestito_reale(self):
        giocatori = [
            _g("Hold", 10_000_000),
            # cartellino ancora della squadra ma giocatore uscito dalla rosa
            _g("Prestito Reale", 40_000_000, squadra_att="Svincolato"),
        ]
        assert _valori_rosa(giocatori, SQUADRA)["valore_rosa_totale"] == "10 Mln"

    def test_include_i_prestiti_in_uscita_fanta(self):
        giocatori = [
            _g("Hold", 10_000_000),
            _g("Fanta-Prestito", 8_000_000, squadra_att="Altra"),
        ]
        assert _valori_rosa(giocatori, SQUADRA)["valore_rosa_totale"] == "18 Mln"


class TestSottototaliDeiRiquadri:
    def test_il_riquadro_rosa_comprende_i_prestiti_in_entrata(self):
        giocatori = [
            _g("Hold", 20_000_000),
            _g("Fanta-Prestito", 15_000_000, detentore="Altra"),
        ]
        valori = _valori_rosa(giocatori, SQUADRA)
        assert valori["valore_rosa"] == "35 Mln"
        assert valori["valore_prestiti_in"] == "15 Mln"

    def test_la_primavera_non_entra_nel_riquadro_rosa(self):
        giocatori = [_g("Hold", 20_000_000), _g("Primavera", 5_000_000)]
        valori = _valori_rosa(giocatori, SQUADRA)
        assert valori["valore_rosa"] == "20 Mln"
        assert valori["valore_primavera"] == "5 Mln"

    def test_il_riquadro_prestiti_out_segue_l_elenco_mostrato(self):
        giocatori = [
            _g("Fanta-Prestito", 8_000_000, squadra_att="Altra"),
            _g("Prestito Reale", 4_000_000, squadra_att="Svincolato"),
        ]
        assert _valori_rosa(giocatori, SQUADRA)["valore_prestiti_out"] == "12 Mln"

    def test_ogni_chiave_e_presente_anche_senza_dati(self):
        valori = _valori_rosa([], SQUADRA)
        assert set(valori) == {
            "valore_rosa_totale", "valore_rosa", "valore_primavera",
            "valore_prestiti_in", "valore_prestiti_out",
        }
        assert all(v is None for v in valori.values())
