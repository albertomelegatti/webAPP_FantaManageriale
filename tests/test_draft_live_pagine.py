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


class TestAccesso:
    def test_senza_login_si_va_al_login(self, app, aperto):
        risposta = app.test_client().get("/draft/live/")
        assert risposta.status_code == 302 and "/login" in risposta.headers["Location"]

    def test_l_admin_puo_guardare(self, app, aperto):
        assert _client(app, admin=True).get("/draft/live/").status_code == 200

    def test_il_bottone_sta_nella_dashboard_della_squadra(self, app, aperto, nome_squadra):
        corpo = _pagina(_client(app, nome_squadra).get(f"/user/squadra_login/{nome_squadra}"))
        assert "/draft/live/" in corpo and "Draft Live" in corpo

    def test_il_bottone_non_compare_se_non_c_e_un_draft_aperto(self, app, cur, db_isolato, draft, nome_squadra):
        # `draft` lo lascia preparato, non aperto.
        corpo = _pagina(_client(app, nome_squadra).get(f"/user/squadra_login/{nome_squadra}"))
        assert "Draft Live" not in corpo
        assert "/draft/live" not in corpo

    def test_il_bottone_e_attivo_a_draft_aperto(self, app, aperto, nome_squadra):
        corpo = _pagina(_client(app, nome_squadra).get(f"/user/squadra_login/{nome_squadra}"))
        assert 'href="/draft/live/"' in corpo and "Draft Live" in corpo

    def test_il_bottone_non_sta_nella_home_pubblica(self, app):
        assert "/draft/live" not in _pagina(app.test_client().get("/"))


class TestPaginaLive:
    def test_senza_draft_non_si_rompe(self, app, cur, db_isolato, nome_squadra):
        cur.execute("DELETE FROM draft_sessione;")
        db_isolato.commit()
        risposta = _client(app, nome_squadra).get("/draft/live/")
        assert risposta.status_code == 200
        assert "Nessun draft in corso" in _pagina(risposta)

    def test_draft_non_aperto(self, app, draft):
        prima, seconda = draft
        risposta = _client(app, prima).get("/draft/live/")
        assert risposta.status_code == 200
        assert "non è ancora aperto" in _pagina(risposta)

    def test_mostra_chi_e_on_the_clock(self, app, aperto):
        prima, seconda = aperto
        corpo = _pagina(_client(app, prima).get("/draft/live/"))
        assert "On the clock" in corpo
        assert seconda in corpo

    def test_il_pool_si_vede_solo_alla_squadra_di_turno(self, app, cur, db_isolato, aperto):
        prima, seconda = aperto
        _giocatore(cur, "Giovane Visibile")
        # Piu' richieste in fila: senza commit la prima, chiudendo la sua transazione,
        # annullerebbe il giocatore appena inserito.
        db_isolato.commit()

        assert "Giovane Visibile" not in _pagina(_client(app, prima).get("/draft/live/"))
        assert "Giovane Visibile" not in _pagina(_client(app, admin=True).get("/draft/live/"))
        corpo = _pagina(_client(app, seconda).get("/draft/live/"))
        assert "Giovane Visibile" in corpo
        assert "È il tuo turno" in corpo

    def test_la_scelta_compare_nel_tabellone(self, app, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Scelto")
        _client(app, seconda).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        assert "Giovane Scelto" in _pagina(_client(app, prima).get("/draft/live/"))


def _id_pick(cur, numero):
    cur.execute("SELECT id FROM draft WHERE numero = %s;", (numero,))
    return cur.fetchone()["id"]


class TestAnimazioneScelta:
    """L'overlay con logo e campioncino: il server decide se mostrarlo."""

    def _scegli_seconda(self, app, cur, seconda, nome="Giovane Animato"):
        g = _giocatore(cur, nome)
        cur.execute("UPDATE giocatore SET id_fantacalcio = 12345 WHERE id = %s;", (g,))
        _client(app, seconda).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1), "id_giocatore": g})
        return g

    def test_senza_scelte_non_c_e_overlay(self, app, aperto):
        prima, seconda = aperto
        assert 'id="dr-overlay"' not in _pagina(_client(app, prima).get("/draft/live/"))

    def test_dopo_una_scelta_l_overlay_mostra_giocatore_squadra_e_foto(self, app, cur, aperto):
        prima, seconda = aperto
        self._scegli_seconda(app, cur, seconda)

        corpo = _pagina(_client(app, prima).get("/draft/live/"))
        assert 'id="dr-overlay"' in corpo
        sezione = corpo[corpo.index('id="dr-overlay"'):]
        assert "Giovane Animato" in sezione and "Pick n. 1" in sezione
        assert "12345.png" in sezione                 # il campioncino
        assert "loghi/" in sezione                    # il logo della squadra

    def test_la_vede_anche_chi_ha_scelto(self, app, cur, aperto):
        prima, seconda = aperto
        self._scegli_seconda(app, cur, seconda)
        assert 'id="dr-overlay"' in _pagina(_client(app, seconda).get("/draft/live/"))

    def test_una_scelta_vecchia_non_si_anima(self, app, cur, db_isolato, aperto):
        prima, seconda = aperto
        self._scegli_seconda(app, cur, seconda)
        cur.execute("UPDATE draft SET scelta_il = now() - interval '1 hour' WHERE numero = 1;")
        db_isolato.commit()
        assert 'id="dr-overlay"' not in _pagina(_client(app, prima).get("/draft/live/"))

    def test_anima_l_ultima_scelta_non_la_prima(self, app, cur, db_isolato, aperto):
        prima, seconda = aperto
        self._scegli_seconda(app, cur, seconda, "Primo Scelto")
        cur.execute("UPDATE draft SET scelta_il = now() - interval '1 minute' WHERE numero = 1;")
        g2 = _giocatore(cur, "Secondo Scelto")
        db_isolato.commit()
        _client(app, prima).post("/draft/live/scegli", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 2), "id_giocatore": g2})

        corpo = _pagina(_client(app, prima).get("/draft/live/"))
        overlay = corpo[corpo.index('id="dr-overlay"'):corpo.index("<script>", corpo.index('id="dr-overlay"'))]
        assert "Secondo Scelto" in overlay and "Pick n. 2" in overlay
        assert "Primo Scelto" not in overlay

    def test_la_pick_saltata_non_si_anima(self, app, cur, aperto):
        prima, seconda = aperto
        _client(app, admin=True).post("/admin/draft/salta", data={
            "anno": ANNO, "id_pick": _id_pick(cur, 1)})
        assert 'id="dr-overlay"' not in _pagina(_client(app, prima).get("/draft/live/"))


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
