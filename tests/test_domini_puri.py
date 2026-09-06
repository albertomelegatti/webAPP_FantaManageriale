"""
Test delle funzioni pure: nessun database, nessuna rete.

Sono la rete di sicurezza più economica del refactoring: queste funzioni si
sposteranno in app/domini/ e app/core/tempo.py, e questi test devono restare
verdi identici prima e dopo lo spostamento.
"""

from datetime import date, datetime, timedelta

import pytest

from app.queries import (
    calcola_eta,
    formatta_data_nascita_con_eta,
    formatta_scadenza_contratto,
    ruolo_base_sort_key,
    ruolo_sort_key,
)
from app.domini.matching_transfermarkt import (
    candidati_esatti,
    candidati_fuzzy,
    cognome_e_iniziale,
    normalizza,
    parse_data_tm,
)
from app.blueprints.user import format_partecipanti, formatta_data
from app.blueprints.prestiti import _get_allowed_prestito_years


# --- Ordinamento dei ruoli ---------------------------------------------------

class TestRuoloSortKey:
    def test_portiere_viene_per_primo(self):
        assert ruolo_sort_key("POR") == 1

    def test_attaccanti_vengono_per_ultimi(self):
        assert ruolo_sort_key("A") == 27
        assert ruolo_sort_key("PC") == 28

    def test_ruolo_sconosciuto_finisce_in_fondo(self):
        assert ruolo_sort_key("XYZ") == 99

    def test_normalizza_spazi_e_maiuscole(self):
        assert ruolo_sort_key(" dd, e ") == 2
        assert ruolo_sort_key("DD,E") == 2

    def test_ordine_relativo_difesa_centrocampo_attacco(self):
        assert ruolo_sort_key("POR") < ruolo_sort_key("DC") < ruolo_sort_key("C") < ruolo_sort_key("A")


class TestRuoloBaseSortKey:
    def test_ordine_dei_ruoli_base(self):
        assert ruolo_base_sort_key("Por") == 0
        assert ruolo_base_sort_key("Pc") == 11

    def test_ruolo_base_sconosciuto_finisce_in_fondo(self):
        assert ruolo_base_sort_key("Zz") == 99

    def test_e_sensibile_alle_maiuscole(self):
        # Comportamento attuale: l'elenco contiene 'Por', non 'POR'.
        assert ruolo_base_sort_key("POR") == 99


# --- Date e formattazione ----------------------------------------------------

def _stessa_data_fra_anni(anni):
    """La data di oggi spostata di N anni, per test deterministici sull'età."""
    oggi = date.today()
    try:
        return oggi.replace(year=oggi.year + anni)
    except ValueError:  # 29 febbraio in un anno non bisestile
        pytest.skip("Data odierna non rappresentabile nell'anno di destinazione (29 febbraio).")


class TestCalcolaEta:
    def test_senza_data_restituisce_none(self):
        assert calcola_eta(None) is None

    def test_compleanno_oggi(self):
        assert calcola_eta(_stessa_data_fra_anni(-30)) == 30

    def test_compleanno_non_ancora_arrivato(self):
        domani = date.today() + timedelta(days=1)
        try:
            nascita = domani.replace(year=domani.year - 30)  # compie 30 anni domani
        except ValueError:
            pytest.skip("Domani è il 29 febbraio: data non rappresentabile 30 anni fa.")
        assert calcola_eta(nascita) == 29


class TestFormattaDataNascitaConEta:
    def test_senza_data_restituisce_none(self):
        assert formatta_data_nascita_con_eta(None) is None

    def test_formato_completo(self):
        assert formatta_data_nascita_con_eta(date(1990, 3, 7)).startswith("07/03/1990 (")
        assert formatta_data_nascita_con_eta(date(1990, 3, 7)).endswith(" anni)")


class TestFormattaScadenzaContratto:
    def test_senza_data_restituisce_none(self):
        assert formatta_scadenza_contratto(None) is None

    def test_data_passata_e_scaduta(self):
        assert formatta_scadenza_contratto(date(2000, 1, 1)) == "Scaduto"

    def test_oggi_e_scaduto(self):
        assert formatta_scadenza_contratto(date.today()) == "Scaduto"

    def test_esattamente_un_anno(self):
        assert formatta_scadenza_contratto(_stessa_data_fra_anni(1)) == "1 anno"

    def test_esattamente_due_anni_usa_il_plurale(self):
        assert formatta_scadenza_contratto(_stessa_data_fra_anni(2)) == "2 anni"


class TestFormattaData:
    def test_none_resta_none(self):
        assert formatta_data(None) is None

    def test_datetime_viene_formattato(self):
        assert formatta_data(datetime(2026, 3, 7, 14, 30)) == "07/03/2026 14:30"

    def test_stringa_iso_con_millisecondi_e_timezone(self):
        assert formatta_data("2026-03-07T14:30:00.123456+02:00") == "07/03/2026 14:30"

    def test_stringa_non_valida_torna_invariata(self):
        assert formatta_data("non una data") == "non una data"


class TestFormatPartecipanti:
    def test_lista_vuota(self):
        assert format_partecipanti([]) == ""
        assert format_partecipanti(None) == ""

    def test_partecipante_singolo(self):
        assert format_partecipanti(["Ajax"]) == "Ajax"

    def test_piu_partecipanti_separati_da_virgola_e_a_capo(self):
        assert format_partecipanti(["Ajax", "Roma"]) == "Ajax,\nRoma"


# --- Anni ammessi per la scadenza dei prestiti -------------------------------

class TestAnniPrestitoAmmessi:
    def test_prima_del_primo_luglio_parte_dall_anno_corrente(self):
        anni, default = _get_allowed_prestito_years(datetime(2026, 1, 15))
        assert anni == [2026, 2027]
        assert default == 2026

    def test_dopo_il_primo_luglio_parte_dall_anno_successivo(self):
        anni, default = _get_allowed_prestito_years(datetime(2026, 8, 15))
        assert anni == [2027, 2028]
        assert default == 2027

    def test_il_primo_luglio_e_ancora_incluso_nell_anno_corrente(self):
        anni, default = _get_allowed_prestito_years(datetime(2026, 7, 1, 12, 0, 0))
        assert default == 2026


# --- Matching Transfermarkt --------------------------------------------------

class TestNormalizza:
    def test_stringa_vuota(self):
        assert normalizza(None) == ""
        assert normalizza("") == ""

    def test_rimuove_accenti(self):
        assert normalizza("Oulaï") == "oulai"
        assert normalizza("Müller") == "muller"

    def test_translittera_lettere_non_decomponibili(self):
        # Senza la tabella TRANSLIT la 'ı' verrebbe cancellata invece che trascritta.
        assert normalizza("Yıldız") == "yildiz"
        assert normalizza("Łukasz") == "lukasz"

    def test_rimuove_punteggiatura_e_normalizza_le_maiuscole(self):
        assert normalizza("D'Ambrosio") == "dambrosio"


class TestCognomeEIniziale:
    def test_cognome_semplice(self):
        assert cognome_e_iniziale("Ambrosino") == ("ambrosino", None)

    def test_cognome_con_iniziale(self):
        assert cognome_e_iniziale("Moro L.") == ("moro", "l")

    def test_iniziale_di_piu_lettere(self):
        assert cognome_e_iniziale("Esposito Se.") == ("esposito", "se")

    def test_cognome_composto_senza_punto_resta_intero(self):
        assert cognome_e_iniziale("Zambo Anguissa") == ("zambo anguissa", None)


class TestParseDataTm:
    def test_data_valida(self):
        assert parse_data_tm("01/07/2000") == date(2000, 7, 1)

    @pytest.mark.parametrize("valore", [None, "", "   ", "-", "boh"])
    def test_valori_non_parsabili(self, valore):
        assert parse_data_tm(valore) is None


def _tm(id_transfermarkt, nome, cognome):
    return {"id_transfermarkt": id_transfermarkt, "nome": nome, "cognome": cognome}


class TestCandidatiEsatti:
    def test_trova_il_cognome_esatto(self):
        rosa = [_tm(1, "Luca", "Moro"), _tm(2, "Marco", "Rossi")]
        assert [c["id_transfermarkt"] for c in candidati_esatti("Moro", rosa)] == [1]

    def test_ambiguita_risolta_dall_iniziale(self):
        rosa = [_tm(1, "Luca", "Moro"), _tm(2, "Nicola", "Moro")]
        assert [c["id_transfermarkt"] for c in candidati_esatti("Moro L.", rosa)] == [1]

    def test_senza_iniziale_restituisce_tutti_gli_omonimi(self):
        rosa = [_tm(1, "Luca", "Moro"), _tm(2, "Nicola", "Moro")]
        assert len(candidati_esatti("Moro", rosa)) == 2

    def test_nessuna_corrispondenza(self):
        assert candidati_esatti("Inesistente", [_tm(1, "Luca", "Moro")]) == []

    def test_iniziale_che_non_filtra_nessuno_lascia_i_candidati(self):
        # Se il filtro per iniziale svuoterebbe la lista, i candidati restano.
        rosa = [_tm(1, "Luca", "Moro"), _tm(2, "Nicola", "Moro")]
        assert len(candidati_esatti("Moro Z.", rosa)) == 2


class TestCandidatiFuzzy:
    def test_trova_per_token_condiviso(self):
        rosa = [_tm(1, "Frank", "Zambo Anguissa")]
        assert [c["id_transfermarkt"] for c in candidati_fuzzy("Anguissa", rosa)] == [1]

    def test_trova_cognome_composto_troncato_diversamente(self):
        rosa = [_tm(1, "Cheick", "Inao Oulaï")]
        assert [c["id_transfermarkt"] for c in candidati_fuzzy("Oulai", rosa)] == [1]

    def test_nessun_token_in_comune(self):
        assert candidati_fuzzy("Rossi", [_tm(1, "Frank", "Anguissa")]) == []
