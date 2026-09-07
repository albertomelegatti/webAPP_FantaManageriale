"""
Schema del form di proposta di scambio: nessun database, nessuna rete.

Sostituisce novanta righe di lettura manuale in cui la stessa logica compariva
quattro volte, una per ogni combinazione dei due blocchi prestito con le loro
parti richiesta e offerta.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError
from werkzeug.datastructures import MultiDict

from app.schemas.scambio import PropostaScambio

ANNI = [2027, 2028]
DEFAULT = 2027


def _form(**campi):
    """Un form come lo consegna Flask, con supporto ai campi ripetuti."""
    md = MultiDict()
    for chiave, valore in campi.items():
        if isinstance(valore, list):
            for v in valore:
                md.add(chiave, v)
        else:
            md.add(chiave, valore)
    return md


def _proposta(**campi):
    return PropostaScambio.da_form(_form(**campi), ANNI, DEFAULT)


class TestCampiBase:
    def test_una_proposta_minima(self):
        p = _proposta(squadra_destinataria="Roma", crediti_offerti="30")
        assert p.squadra_destinataria == "Roma"
        assert p.crediti_offerti == 30
        assert p.crediti_richiesti == 0

    def test_i_campi_numerici_vuoti_valgono_zero(self):
        p = _proposta(squadra_destinataria="Roma", crediti_offerti="", crediti_richiesti="")
        assert (p.crediti_offerti, p.crediti_richiesti) == (0, 0)

    def test_un_valore_non_numerico_non_fa_fallire_la_richiesta(self):
        """Prima int('abc') sollevava ValueError e la richiesta finiva in errore."""
        p = _proposta(squadra_destinataria="Roma", crediti_offerti="abc")
        assert p.crediti_offerti == 0

    def test_gli_elenchi_scartano_i_valori_non_numerici(self):
        p = _proposta(squadra_destinataria="Roma",
                      giocatori_offerti=["12", "abc", "34", ""])
        assert p.giocatori_offerti == [12, 34]

    def test_il_messaggio_viene_ripulito_dagli_spazi(self):
        assert _proposta(squadra_destinataria="Roma", messaggio="  ciao  ").messaggio == "ciao"

    def test_senza_squadra_destinataria_la_proposta_e_invalida(self):
        with pytest.raises(ValidationError):
            _proposta(crediti_offerti="10")


class TestProposteVuote:
    def test_una_proposta_senza_nulla_e_vuota(self):
        assert _proposta(squadra_destinataria="Roma").e_vuota

    def test_bastano_dei_crediti_offerti(self):
        assert not _proposta(squadra_destinataria="Roma", crediti_offerti="5").e_vuota

    def test_basta_una_pick_richiesta(self):
        assert not _proposta(squadra_destinataria="Roma", pick_richiesta=["7"]).e_vuota

    def test_offerta_e_richiesta_si_valutano_separatamente(self):
        p = _proposta(squadra_destinataria="Roma", giocatori_offerti=["1"])
        assert not p.offerta_vuota
        assert p.richiesta_vuota
        assert not p.e_vuota


class TestPrestitiNellaProposta:
    def _con_prestito(self, verso, **extra):
        suffisso = "richiesta" if verso == "richiesto" else "offerta"
        campi = {
            "squadra_destinataria": "Roma",
            "enable_prestito1": "on",
            f"prestito1_{verso}": "42",
            f"prestito1_tipo_{verso}": extra.pop("tipo", "Secco"),
            f"prestito1_data_fine_{suffisso}": extra.pop("anno", "2028"),
        }
        campi.update(extra)
        return _proposta(**campi)

    def test_un_prestito_richiesto_finisce_fra_i_richiesti(self):
        p = self._con_prestito("richiesto")
        assert len(p.prestiti_richiesti) == 1 and not p.prestiti_offerti
        assert p.prestiti_richiesti[0].giocatore == 42

    def test_un_prestito_offerto_finisce_fra_gli_offerti(self):
        p = self._con_prestito("offerto")
        assert len(p.prestiti_offerti) == 1 and not p.prestiti_richiesti

    def test_le_etichette_del_menu_diventano_valori_del_database(self):
        assert self._con_prestito("richiesto", tipo="Con diritto di riscatto") \
            .prestiti_richiesti[0].tipo == "diritto_di_riscatto"
        assert self._con_prestito("richiesto", tipo="Con obbligo di riscatto") \
            .prestiti_richiesti[0].tipo == "obbligo_di_riscatto"

    def test_un_prestito_secco_azzera_il_riscatto(self):
        """Regola di gioco: il secco non prevede riscatto, qualunque cifra sia
        stata inserita nel form."""
        p = self._con_prestito("richiesto", tipo="Secco", prestito1_riscatto_richiesto="50")
        assert p.prestiti_richiesti[0].crediti_riscatto == 0

    def test_un_prestito_con_diritto_conserva_il_riscatto(self):
        p = self._con_prestito("richiesto", tipo="Con diritto di riscatto",
                               prestito1_riscatto_richiesto="50")
        assert p.prestiti_richiesti[0].crediti_riscatto == 50

    def test_la_scadenza_e_il_primo_luglio_dell_anno_scelto(self):
        p = self._con_prestito("richiesto", anno="2028")
        assert p.prestiti_richiesti[0].data_fine == datetime(2028, 7, 1, 23, 59, 59)

    def test_un_anno_non_ammesso_ricade_sul_predefinito(self):
        """Il campo arriva da un menu a tendina: un valore diverso significa
        richiesta manipolata, non errore dell'utente."""
        p = self._con_prestito("richiesto", anno="1999")
        assert p.prestiti_richiesti[0].data_fine.year == DEFAULT

    def test_senza_il_blocco_abilitato_il_prestito_viene_ignorato(self):
        p = _proposta(squadra_destinataria="Roma", prestito1_richiesto="42",
                      prestito1_tipo_richiesto="Secco")
        assert not p.prestiti_richiesti and not p.prestiti_offerti

    def test_un_prestito_senza_tipo_viene_ignorato(self):
        p = _proposta(squadra_destinataria="Roma", enable_prestito1="on",
                      prestito1_richiesto="42", prestito1_tipo_richiesto="")
        assert not p.prestiti_richiesti

    def test_i_due_blocchi_sono_indipendenti(self):
        p = _proposta(squadra_destinataria="Roma",
                      enable_prestito1="on", prestito1_richiesto="1",
                      prestito1_tipo_richiesto="Secco", prestito1_data_fine_richiesta="2027",
                      enable_prestito2="on", prestito2_offerto="2",
                      prestito2_tipo_offerto="Secco", prestito2_data_fine_offerta="2027")
        assert len(p.prestiti_richiesti) == 1 and len(p.prestiti_offerti) == 1

    def test_un_prestito_rende_la_proposta_non_vuota(self):
        assert not self._con_prestito("richiesto").e_vuota


class TestValoriMalformati:
    """Casi che non arrivano da un utente normale ma da un form manomesso o da
    un browser che invia qualcosa di inatteso."""

    def test_un_anno_non_numerico_ricade_sul_predefinito(self):
        p = _proposta(squadra_destinataria="Roma", enable_prestito1="on",
                      prestito1_richiesto="42", prestito1_tipo_richiesto="Secco",
                      prestito1_data_fine_richiesta="non-un-anno")
        assert p.prestiti_richiesti[0].data_fine.year == DEFAULT

    def test_un_anno_mancante_ricade_sul_predefinito(self):
        p = _proposta(squadra_destinataria="Roma", enable_prestito1="on",
                      prestito1_richiesto="42", prestito1_tipo_richiesto="Secco")
        assert p.prestiti_richiesti[0].data_fine.year == DEFAULT

    def test_un_tipo_di_prestito_sconosciuto_fa_ignorare_il_prestito(self):
        """Meglio scartare il prestito che salvarlo con un tipo che l'enum del
        database non accetta."""
        p = _proposta(squadra_destinataria="Roma", enable_prestito1="on",
                      prestito1_richiesto="42",
                      prestito1_tipo_richiesto="Tipo Inventato",
                      prestito1_data_fine_richiesta="2027")
        assert not p.prestiti_richiesti
