"""
Filtro U21 nella pagina "nuova_asta".

Da regolamento (app/regolamento.txt): il listone chiamabile in asta esclude gli
U21, acquistabili solo tramite draft. La soglia è configurabile dall'admin
(general_config.u21_threshold_year): sono considerati U21 i giocatori nati
nell'anno della soglia o dopo.
"""

import json
import re

import pytest

pytestmark = pytest.mark.db


def _crea_giocatore_svincolato(cur, nome, anno_nascita):
    """Crea un giocatore svincolato, non ancora in asta, con l'anno di nascita
    indicato (None per un giocatore senza data di nascita sincronizzata)."""
    cur.execute(
        """INSERT INTO giocatore (
               nome, ruolo, tipo_contratto, squadra_att, detentore_cartellino,
               quot_att_mantra, costo, priorita, club, data_nascita
           )
           VALUES (%s, ARRAY['PlaceHolderRole']::ruolo_mantra[], 'Svincolato',
                   'Svincolato', 'Svincolato', 1, 0, 1, 'Test', %s)
           RETURNING id;""",
        (nome, f"{anno_nascita}-06-15" if anno_nascita is not None else None),
    )
    return cur.fetchone()["id"]


def _nomi_giocatori_in_pagina(risposta):
    """Estrae i nomi dal JSON dei giocatori incorporato nella pagina (la lista
    passata al form di ricerca via `giocatori_info_per_asta|tojson`)."""
    corpo = risposta.get_data(as_text=True)
    match = re.search(r"JSON\.parse\('(.*)'\)", corpo)
    assert match, "JSON dei giocatori non trovato nella pagina nuova_asta"
    giocatori = json.loads(match.group(1))
    return {g["nome"] for g in giocatori}


def _pagina_nuova_asta(app, nome_squadra):
    client = app.test_client()
    with client.session_transaction() as s:
        s.update(logged_in=True, is_admin=False, nome_squadra=nome_squadra, username="test")
    return client.get(f"/aste/nuova_asta/{nome_squadra}")


class TestFiltroU21NuovaAsta:
    def test_giocatore_nato_nell_anno_soglia_o_dopo_non_compare(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        nome_u21 = "Test Filtro U21 Under"
        nome_non_u21 = "Test Filtro U21 Over"
        _crea_giocatore_svincolato(cur, nome_u21, 2005)  # nato dopo la soglia: U21
        _crea_giocatore_svincolato(cur, nome_non_u21, 1998)  # nato prima della soglia
        db_isolato.commit()

        nomi = _nomi_giocatori_in_pagina(_pagina_nuova_asta(app, nome_squadra))

        assert nome_non_u21 in nomi
        assert nome_u21 not in nomi

    def test_giocatore_nato_esattamente_nell_anno_soglia_e_escluso(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        """La soglia è inclusiva: nato nell'anno u21_threshold_year -> U21."""
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        nome_soglia = "Test Filtro U21 Soglia"
        _crea_giocatore_svincolato(cur, nome_soglia, 2003)
        db_isolato.commit()

        nomi = _nomi_giocatori_in_pagina(_pagina_nuova_asta(app, nome_squadra))

        assert nome_soglia not in nomi

    def test_senza_soglia_configurata_nessun_filtro_viene_applicato(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        cur.execute("UPDATE general_config SET u21_threshold_year = NULL WHERE id = 1;")
        nome_giovane = "Test Filtro U21 SenzaSoglia"
        _crea_giocatore_svincolato(cur, nome_giovane, 2010)
        db_isolato.commit()

        nomi = _nomi_giocatori_in_pagina(_pagina_nuova_asta(app, nome_squadra))

        assert nome_giovane in nomi

    def test_giocatore_senza_data_nascita_non_viene_escluso(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        """Un giocatore non ancora sincronizzato con Transfermarkt (data di
        nascita mancante) non deve sparire dal listone per un falso positivo."""
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        nome_senza_data = "Test Filtro U21 SenzaData"
        _crea_giocatore_svincolato(cur, nome_senza_data, None)
        db_isolato.commit()

        nomi = _nomi_giocatori_in_pagina(_pagina_nuova_asta(app, nome_squadra))

        assert nome_senza_data in nomi
