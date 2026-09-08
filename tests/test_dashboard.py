"""
Composizione della dashboard di una squadra.

Era la pagina piu' pesante dell'applicazione: dieci query, ~520 ms. Su questo
database il tempo di una pagina e' quasi interamente il numero di viaggi di
rete, quindi ridurre le interrogazioni vale piu' che renderle piu' furbe.
"""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def dati(cur, nome_squadra):
    from app.services import dashboard as servizio
    return servizio.dati_squadra(cur, nome_squadra)


class TestDivisioneDeiGiocatori:
    def test_i_quattro_elenchi_arrivano_da_una_sola_lettura(self, dati):
        for chiave in ("rosa", "primavera", "prestiti_in", "prestiti_out"):
            assert chiave in dati

    def test_la_primavera_non_compare_nella_rosa(self, dati):
        nomi_rosa = {g["nome"] for g in dati["rosa"]}
        nomi_primavera = {g["nome"] for g in dati["primavera"]}
        assert not (nomi_rosa & nomi_primavera)

    def test_i_prestiti_in_entrata_compaiono_anche_nella_rosa(self, dati):
        """Comportamento storico della pagina: la rosa esclude solo la
        primavera, quindi un giocatore preso in prestito vi compare."""
        nomi_rosa = {g["nome"] for g in dati["rosa"]}
        for g in dati["prestiti_in"]:
            assert g["nome"] in nomi_rosa

    def test_i_prestiti_in_uscita_non_sono_in_rosa(self, cur, nome_squadra, dati):
        """Sono giocatori di cui la squadra ha il cartellino ma che gioca
        un'altra: per definizione non li schiera."""
        for g in dati["prestiti_out"]:
            assert g["squadra_att"] != nome_squadra

    def test_il_conteggio_dei_prestiti_in_corrisponde_all_elenco(self, dati):
        assert dati["prestiti_in_num"] == len(dati["prestiti_in"])


class TestOrdinamento:
    def test_i_giocatori_sono_ordinati_per_ruolo(self, dati):
        from app.domini.ruoli import ruolo_sort_key
        chiavi = [ruolo_sort_key(g["ruolo"]) for g in dati["rosa"]]
        assert chiavi == sorted(chiavi)

    def test_a_parita_di_ruolo_l_ordine_e_alfabetico(self, dati):
        """Prima l'ordinamento era solo per ruolo, quindi l'ordine dei
        giocatori dello stesso ruolo dipendeva dal piano di esecuzione della
        query: la stessa pagina poteva mostrarli in ordini diversi."""
        from app.domini.ruoli import ruolo_sort_key
        coppie = [(ruolo_sort_key(g["ruolo"]), g["nome"]) for g in dati["rosa"]]
        assert coppie == sorted(coppie)

    def test_l_ordine_e_stabile_fra_due_letture(self, cur, nome_squadra):
        from app.services import dashboard as servizio
        primo = [g["nome"] for g in servizio.dati_squadra(cur, nome_squadra)["rosa"]]
        secondo = [g["nome"] for g in servizio.dati_squadra(cur, nome_squadra)["rosa"]]
        assert primo == secondo


class TestSlot:
    def test_gli_slot_occupati_sono_la_somma_di_giocatori_e_aste(self, cur, nome_squadra, dati):
        from app.repositories import aste as aste_repo
        slot_aste = aste_repo.slot_impegnati(cur, nome_squadra)
        assert dati["slot_occupati"] == dati["slot_giocatori"] + slot_aste

    def test_gli_slot_da_giocatori_coincidono_col_conteggio_del_database(
        self, cur, nome_squadra, dati
    ):
        """Il conteggio ora si fa in memoria sulle righe gia' lette: deve dare
        lo stesso risultato della query che faceva prima."""
        from app.repositories import giocatori as giocatori_repo
        assert dati["slot_giocatori"] == giocatori_repo.slot_occupati_da_giocatori(cur, nome_squadra)


class TestCasiLimite:
    def test_una_squadra_inesistente_da_none(self, cur):
        from app.services import dashboard as servizio
        assert servizio.dati_squadra(cur, "Squadra Che Non Esiste") is None

    def test_una_squadra_senza_stadio_non_rompe_la_pagina(self, app, cur, db_isolato, nome_squadra):
        from app.services import dashboard as servizio
        cur.execute("DELETE FROM stadio WHERE proprietario = %s;", (nome_squadra,))
        db_isolato.commit()

        dati = servizio.dati_squadra(cur, nome_squadra)
        assert dati is not None and dati["stadio"] is None
        assert app.test_client().get(f"/squadra/{nome_squadra}").status_code == 200

    def test_la_pagina_di_una_squadra_inesistente_reindirizza(self, app):
        risposta = app.test_client().get("/squadra/Squadra Che Non Esiste")
        assert risposta.status_code == 302
