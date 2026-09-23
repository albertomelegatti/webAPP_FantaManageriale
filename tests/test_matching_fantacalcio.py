"""Test per app/domini/matching_fantacalcio.py e url_campioncino: funzioni pure, nessun database."""

from app.core.formato import url_campioncino
from app.domini.matching_fantacalcio import (NESSUNA_CORRISPONDENZA, candidati_esatti,
                                              candidati_stesso_club, sigla_club)


def _fc(id_, nome, squadra):
    return {"id_fantacalcio": id_, "nome": nome, "squadra_fc": squadra}


class TestSiglaClub:
    def test_inizio_del_nome(self):
        assert sigla_club("Milan") == "MIL"
        assert sigla_club("Torino") == "TOR"

    def test_eccezione(self):
        assert sigla_club("Hellas Verona") == "VER"


class TestCandidatiEsatti:
    def test_nome_normalizzato(self):
        listone = [_fc(1, "Kessiè", "ATA"), _fc(2, "Kessie X.", "MIL")]
        assert candidati_esatti("Kessie", listone) == [listone[0]]

    def test_spazio_in_fondo_al_nome(self):
        assert candidati_esatti("Buksa ", [_fc(1, "Buksa", "UDI")]) != []


class TestCandidatiStessoClub:
    def test_nome_e_club_uguali(self):
        listone = [_fc(1, "Paleari", "TOR")]
        assert candidati_stesso_club("Paleari", "Torino", listone) == listone

    def test_omonimo_di_un_altro_club_escluso(self):
        # stesso nome, club diverso: potrebbe essere un'altra persona
        assert candidati_stesso_club("Fini", "Genoa", [_fc(1, "Fini", "FRO")]) == []

    def test_sceglie_l_omonimo_del_club_giusto(self):
        listone = [_fc(1, "Martin", "GEN"), _fc(2, "Martin", "LEC")]
        assert candidati_stesso_club("Martin", "Genoa", listone) == [listone[0]]

    def test_club_mancante(self):
        assert candidati_stesso_club("Paleari", None, [_fc(1, "Paleari", "TOR")]) == []


class TestUrlCampioncino:
    def test_id_vero(self):
        assert url_campioncino(4871).endswith("/card/4871.png")

    def test_non_abbinato(self):
        assert url_campioncino(None) is None

    def test_nessuna_corrispondenza(self):
        assert url_campioncino(NESSUNA_CORRISPONDENZA) is None
