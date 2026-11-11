"""Dashboard squadra: le voci sono in sezioni a elenco, come nella home admin, e quelle
che stavano nei sottomenu (Mercato, Prestiti, Gestione Rosa) sono direttamente qui."""

from datetime import date

import pytest

pytestmark = pytest.mark.db

APERTO = {"mercato_aperto": True, "aste_aperte": True, "mercato_chiusura": None,
          "aste_chiusura": None, "u21_threshold_year": None}
CHIUSO = {"mercato_aperto": False, "aste_aperte": False, "mercato_chiusura": date(2026, 9, 2),
          "aste_chiusura": date(2026, 9, 3), "u21_threshold_year": None}


@pytest.fixture
def gate(monkeypatch):
    """Imposta lo stato di mercato e aste letto dalla dashboard."""
    from app.repositories import configurazione as configurazione_repo

    def imposta(stato):
        monkeypatch.setattr(configurazione_repo, "stato_gate", lambda cur: dict(stato))
    return imposta


def _dashboard(client_squadra, nome_squadra):
    risposta = client_squadra.get(f"/user/squadra_login/{nome_squadra}")
    assert risposta.status_code == 200
    return risposta.get_data(as_text=True)


def _link(app, endpoint, nome_squadra):
    from flask import url_for
    with app.test_request_context():
        return url_for(endpoint, nome_squadra=nome_squadra)


# I vecchi sottomenu: le loro voci stanno ora direttamente in dashboard.
SOTTOMENU_ELIMINATI = ("mercato_menu", "rosa_menu", "prestiti_menu")

VOCI_MERCATO = [("aste.user_aste", "Aste"), ("mercato.user_mercato", "Proposte di mercato"),
                ("prestiti.user_prestiti", "Richieste di prestito")]
VOCI_SEMPRE_APERTE = [("rosa.user_gestione_prestiti", "Gestione prestiti"),
                      ("formazione.user_formazione", "Formazione"),
                      ("rosa.user_tagli", "Gestione contratti"), ("rosa.user_primavera", "Primavera"),
                      ("rosa.user_vetrina", "Vetrina")]


class TestMenuSezioni:
    def test_tre_sezioni_a_elenco(self, client_squadra, nome_squadra, gate):
        gate(APERTO)
        corpo = _dashboard(client_squadra, nome_squadra)
        assert corpo.count('class="hm-sezione"') == 3
        for sezione in ("Mercato", "Rosa", "Altro"):
            assert f">{sezione}</h3>" in corpo

    def test_le_voci_dei_sottomenu_stanno_in_dashboard(self, app, client_squadra, nome_squadra, gate):
        gate(APERTO)
        corpo = _dashboard(client_squadra, nome_squadra)
        for endpoint, titolo in VOCI_MERCATO + VOCI_SEMPRE_APERTE:
            assert titolo in corpo
            assert f'href="{_link(app, endpoint, nome_squadra)}"' in corpo

    def test_non_ci_sono_piu_i_bottoni_dei_sottomenu(self, app, client_squadra, nome_squadra, gate):
        gate(APERTO)
        corpo = _dashboard(client_squadra, nome_squadra)
        for pagina in SOTTOMENU_ELIMINATI:
            assert f"/user/{pagina}/" not in corpo

    def test_account(self, client_squadra, nome_squadra, gate):
        gate(APERTO)
        corpo = _dashboard(client_squadra, nome_squadra)
        assert 'href="/cambia_password"' in corpo and 'href="/logout"' in corpo

    def test_a_mercato_e_aste_aperti_nessuna_voce_e_chiusa(self, client_squadra, nome_squadra, gate):
        gate(APERTO)
        assert "hm-riga-chiusa" not in _dashboard(client_squadra, nome_squadra)


class TestVociChiuse:
    def test_a_mercato_e_aste_chiusi_le_voci_spariscono(self, app, client_squadra, nome_squadra, gate):
        gate(CHIUSO)
        corpo = _dashboard(client_squadra, nome_squadra)

        for endpoint, titolo in VOCI_MERCATO:
            assert _link(app, endpoint, nome_squadra) not in corpo
        for descrizione in ("Aste in corso e nuove chiamate", "Scambi con le altre squadre",
                            "Proponi e rispondi ai prestiti"):
            assert descrizione not in corpo
        assert "hm-riga-chiusa" not in corpo and "Chiuso" not in corpo

    def test_chiude_solo_cio_che_e_chiuso(self, app, client_squadra, nome_squadra, gate):
        gate({**APERTO, "aste_aperte": False})     # aste chiuse, mercato aperto
        corpo = _dashboard(client_squadra, nome_squadra)
        assert "Aste in corso" not in corpo
        assert "Proposte di mercato" in corpo and "Richieste di prestito" in corpo

        gate({**APERTO, "mercato_aperto": False})  # mercato chiuso, aste aperte
        corpo = _dashboard(client_squadra, nome_squadra)
        assert "Aste in corso" in corpo
        assert "Proposte di mercato" not in corpo and "Richieste di prestito" not in corpo

    def test_le_altre_voci_restano(self, app, client_squadra, nome_squadra, gate):
        gate(CHIUSO)
        corpo = _dashboard(client_squadra, nome_squadra)
        for endpoint, titolo in VOCI_SEMPRE_APERTE:
            assert f'href="{_link(app, endpoint, nome_squadra)}"' in corpo
        assert corpo.count('class="hm-sezione"') == 3   # Mercato resta: c'e' Gestione prestiti


# Le pagine che si aprono dal menu: tornando indietro si deve arrivare alla dashboard,
# non ai vecchi sottomenu (Mercato, Prestiti, Gestione Rosa) che il menu non usa piu'.
PAGINE_INTERNE = ["aste.user_aste", "mercato.user_mercato", "prestiti.user_prestiti",
                  "rosa.user_gestione_prestiti", "rosa.user_tagli", "rosa.user_primavera",
                  "rosa.user_vetrina"]


class TestIndietro:
    @pytest.mark.parametrize("endpoint", PAGINE_INTERNE)
    def test_l_indietro_porta_alla_dashboard(self, app, client_squadra, nome_squadra, gate_aperto, endpoint):
        risposta = client_squadra.get(_link(app, endpoint, nome_squadra))
        assert risposta.status_code == 200
        corpo = risposta.get_data(as_text=True)

        assert f'href="{_link(app, "user.squadra_login", nome_squadra)}"' in corpo
        for pagina in SOTTOMENU_ELIMINATI:
            assert f"/user/{pagina}/" not in corpo


class TestPosizioneVetrina:
    def test_la_vetrina_sta_nella_sezione_mercato(self, app, client_squadra, nome_squadra, gate):
        gate(APERTO)
        corpo = _dashboard(client_squadra, nome_squadra)
        mercato = corpo[corpo.index(">Mercato</h3>"):corpo.index(">Rosa</h3>")]
        rosa = corpo[corpo.index(">Rosa</h3>"):corpo.index(">Altro</h3>")]
        link = f'href="{_link(app, "rosa.user_vetrina", nome_squadra)}"'
        assert link in mercato and link not in rosa


class TestSottomenuEliminati:
    @pytest.mark.parametrize("pagina", SOTTOMENU_ELIMINATI)
    def test_le_vecchie_pagine_non_esistono_piu(self, app, pagina):
        # Non si prova l'indirizzo con il client: l'app serve ogni eccezione, 404 compresi,
        # come pagina d'errore 500. Basta guardare che la route non sia piu' registrata.
        percorsi = [str(regola) for regola in app.url_map.iter_rules()]
        assert not any(f"/{pagina}/" in percorso for percorso in percorsi)
