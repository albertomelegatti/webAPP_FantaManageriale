"""Draft live, pagine: tabellone pubblico, scelta della squadra, area admin.

Stesso scenario del servizio (due squadre, sei pick, `seconda` sceglie per
prima). Tutto in transazione annullata a fine test.
"""

import pytest

# Le fixture `draft` e `aperto` vengono dal file del servizio: lo scenario e' lo stesso.
from tests.test_draft_live_servizio import ANNO, _giocatore, aperto, draft  # noqa: F401

pytestmark = pytest.mark.db


def _client(app, squadra=None, admin=False):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logged_in"] = squadra is not None or admin
        s["is_admin"] = admin
        s["username"] = "admin" if admin else "test"
        if squadra:
            s["nome_squadra"] = squadra
    return c


def _pagina(risposta):
    return risposta.get_data(as_text=True)


def _stato_pick(cur, numero):
    cur.execute("SELECT id_giocatore_scelto, saltata FROM draft WHERE numero = %s;", (numero,))
    return cur.fetchone()


class TestPaginaPubblica:
    def test_senza_draft_non_si_rompe(self, app, cur, db_isolato):
        cur.execute("DELETE FROM draft_sessione;")
        db_isolato.commit()
        risposta = app.test_client().get("/draft/live/")
        assert risposta.status_code == 200
        assert "Nessun draft in corso" in _pagina(risposta)

    def test_draft_non_aperto(self, app, draft):
        risposta = app.test_client().get("/draft/live/")
        assert risposta.status_code == 200
        assert "non è ancora aperto" in _pagina(risposta)

    def test_mostra_chi_e_on_the_clock(self, app, aperto):
        prima, seconda = aperto
        corpo = _pagina(app.test_client().get("/draft/live/"))
        assert "On the clock" in corpo
        assert seconda in corpo

    def test_il_pool_si_vede_solo_alla_squadra_di_turno(self, app, cur, db_isolato, aperto):
        prima, seconda = aperto
        _giocatore(cur, "Giovane Visibile")
        # Piu' richieste in fila: senza commit la prima, chiudendo la sua transazione,
        # annullerebbe il giocatore appena inserito.
        db_isolato.commit()

        assert "Giovane Visibile" not in _pagina(app.test_client().get("/draft/live/"))
        assert "Giovane Visibile" not in _pagina(_client(app, prima).get("/draft/live/"))
        corpo = _pagina(_client(app, seconda).get("/draft/live/"))
        assert "Giovane Visibile" in corpo
        assert "È il tuo turno" in corpo

    def test_la_scelta_compare_nel_tabellone(self, app, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Scelto")
        _client(app, seconda).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert "Giovane Scelto" in _pagina(app.test_client().get("/draft/live/"))


def _id_pick(cur, numero):
    cur.execute("SELECT id FROM draft WHERE numero = %s;", (numero,))
    return cur.fetchone()["id"]


class TestScelta:
    def test_senza_login_si_va_al_login(self, app, cur, aperto):
        g = _giocatore(cur, "Giovane Uno")
        risposta = app.test_client().post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert risposta.status_code == 302 and "/login" in risposta.headers["Location"]
        assert _stato_pick(cur, 1)["id_giocatore_scelto"] is None

    def test_la_squadra_di_turno_sceglie(self, app, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        risposta = _client(app, seconda).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert risposta.status_code == 302
        assert _stato_pick(cur, 1)["id_giocatore_scelto"] == g

    def test_un_altra_squadra_non_puo_scegliere(self, app, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        _client(app, prima).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert _stato_pick(cur, 1)["id_giocatore_scelto"] is None

    def test_un_admin_non_sceglie_da_qui(self, app, cur, aperto):
        g = _giocatore(cur, "Giovane Uno")
        risposta = _client(app, admin=True).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert risposta.status_code == 302
        assert _stato_pick(cur, 1)["id_giocatore_scelto"] is None

    def test_richiesta_malformata(self, app, aperto):
        prima, seconda = aperto
        risposta = _client(app, seconda).post("/draft/live/scegli", data={"anno": "x"})
        assert risposta.status_code == 302


class TestAdmin:
    def test_solo_admin(self, app, aperto):
        prima, seconda = aperto
        assert app.test_client().get("/admin/draft").status_code == 302
        assert _client(app, prima).get("/admin/draft").status_code == 302
        assert _client(app, admin=True).get("/admin/draft").status_code == 200

    def test_la_pagina_mostra_stato_e_pool(self, app, cur, aperto):
        _giocatore(cur, "Giovane Admin")
        corpo = _pagina(_client(app, admin=True).get(f"/admin/draft?anno={ANNO}"))
        assert "Aperto" in corpo or "aperto" in corpo
        assert "Giovane Admin" in corpo
        assert "Salta la pick" in corpo

    def test_anteprima_senza_classifica(self, app, cur, draft):
        cur.execute("DELETE FROM albo_oro WHERE stagione = '30-31';")
        corpo = _pagina(_client(app, admin=True).get(f"/admin/draft?anno={ANNO}"))
        assert "Manca la classifica del Campionato 30-31" in corpo

    def test_genera_ordine_dalla_classifica(self, app, cur, draft):
        prima, seconda = draft
        cur.execute("DELETE FROM albo_oro WHERE stagione = '30-31';")
        for squadra, pos in ((prima, 2), (seconda, 1)):   # classifica ribaltata rispetto alla fixture
            cur.execute("""INSERT INTO albo_oro (stagione, competizione, fase, squadra, posizione, crediti_generati)
                           VALUES ('30-31', 'Campionato', NULL, %s, %s, 0);""", (squadra, pos))
        _client(app, admin=True).post("/admin/draft/genera", data={"anno": ANNO})

        cur.execute("SELECT detentore_originale FROM draft WHERE numero = 1;")
        assert cur.fetchone()["detentore_originale"] == prima   # ora e' prima, che ha chiuso ultima

    def test_genera_senza_classifica_non_scrive(self, app, cur, draft):
        cur.execute("DELETE FROM albo_oro WHERE stagione = '30-31';")
        _client(app, admin=True).post("/admin/draft/genera", data={"anno": ANNO})
        cur.execute("SELECT detentore_originale FROM draft WHERE numero = 1;")
        assert cur.fetchone() is not None   # i numeri della fixture sono rimasti

    def test_apri_il_draft(self, app, cur, draft):
        _client(app, admin=True).post("/admin/draft/apri", data={"anno": ANNO})
        cur.execute("SELECT stato FROM draft_sessione WHERE anno = %s;", (ANNO,))
        assert cur.fetchone()["stato"] == "aperto"

    def test_l_admin_sceglie_per_l_assente(self, app, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        _client(app, admin=True).post("/admin/draft/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert _stato_pick(cur, 1)["id_giocatore_scelto"] == g
        cur.execute("SELECT scelta_da FROM draft WHERE numero = 1;")
        assert cur.fetchone()["scelta_da"] == "admin:admin"

    def test_l_admin_salta_la_pick(self, app, cur, aperto):
        _client(app, admin=True).post("/admin/draft/salta", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1)})
        assert _stato_pick(cur, 1)["saltata"] is True

    def test_le_azioni_admin_sono_riservate(self, app, cur, aperto):
        prima, seconda = aperto
        _client(app, seconda).post("/admin/draft/salta", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1)})
        assert _stato_pick(cur, 1)["saltata"] is False
