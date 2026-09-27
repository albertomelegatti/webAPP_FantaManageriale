"""
Storico delle rose (giocatore_storico): il trigger sul cambio di detentore del
cartellino e la pagina admin che completa le date di arrivo mancanti.

Lo script CronJob/giocatore_storico_schema.sql viene eseguito dentro la
transazione isolata di ogni test, cosi' si prova la versione del file anche se
il DB di sviluppo ne ha una precedente: lo script e' idempotente, e il DDL in
PostgreSQL e' transazionale, quindi sparisce col rollback finale insieme a
tutto il resto.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.db

SCRIPT_SCHEMA = Path(__file__).resolve().parent.parent / "CronJob" / "giocatore_storico_schema.sql"


@pytest.fixture
def schema(cur, db_isolato):
    # BEGIN/COMMIT dello script chiuderebbero la transazione del test.
    sql = re.sub(r"^(BEGIN|COMMIT);$", "", SCRIPT_SCHEMA.read_text(encoding="utf-8"), flags=re.MULTILINE)
    cur.execute(sql)
    db_isolato.commit()


def _giocatore_in_rosa(cur, squadra):
    cur.execute(
        """SELECT id FROM giocatore
           WHERE detentore_cartellino = %s AND squadra_att = %s AND tipo_contratto = 'Indeterminato'
           LIMIT 1;""",
        (squadra, squadra))
    riga = cur.fetchone()
    if not riga:
        pytest.skip(f"Nessun giocatore in rosa per {squadra}.")
    return riga["id"]


def _altra_squadra(cur, squadra):
    cur.execute("SELECT nome FROM squadra WHERE nome NOT IN (%s, 'Svincolato') LIMIT 1;", (squadra,))
    return cur.fetchone()["nome"]


def _storico(cur, id_giocatore):
    cur.execute(
        "SELECT id, squadra, dal, al, fonte FROM giocatore_storico WHERE giocatore = %s ORDER BY id;",
        (id_giocatore,))
    return cur.fetchall()


def _aperta(cur, id_giocatore):
    return [r for r in _storico(cur, id_giocatore) if r["al"] is None]


def _client_admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=True, username="admin")
    return c


class TestTrigger:
    def test_ogni_giocatore_in_rosa_ha_una_permanenza_aperta(self, cur, schema, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        aperte = _aperta(cur, giocatore)
        assert len(aperte) == 1
        assert aperte[0]["squadra"] == nome_squadra

    def test_cambio_di_detentore_chiude_e_apre(self, cur, schema, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        altra = _altra_squadra(cur, nome_squadra)

        cur.execute("UPDATE giocatore SET detentore_cartellino = %s, squadra_att = %s WHERE id = %s;",
                    (altra, altra, giocatore))

        storico = _storico(cur, giocatore)
        chiusa = [r for r in storico if r["squadra"] == nome_squadra][-1]
        assert chiusa["al"] is not None
        aperte = _aperta(cur, giocatore)
        assert len(aperte) == 1
        assert aperte[0]["squadra"] == altra
        assert aperte[0]["dal"] is not None
        assert aperte[0]["fonte"] == "automatico"

    def test_svincolo_chiude_senza_aprire(self, cur, schema, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)

        cur.execute("UPDATE giocatore SET detentore_cartellino = 'Svincolato', squadra_att = 'Svincolato' WHERE id = %s;",
                    (giocatore,))

        assert _aperta(cur, giocatore) == []

    def test_prestito_non_tocca_lo_storico(self, cur, schema, nome_squadra):
        """Cambia solo squadra_att: il cartellino resta, la permanenza pure."""
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        prima = _storico(cur, giocatore)

        cur.execute("UPDATE giocatore SET squadra_att = %s, tipo_contratto = 'Fanta-Prestito' WHERE id = %s;",
                    (_altra_squadra(cur, nome_squadra), giocatore))

        assert _storico(cur, giocatore) == prima

    def test_rinomina_squadra_non_azzera_la_permanenza(self, cur, schema, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        cur.execute("UPDATE giocatore_storico SET dal = '2025-01-01' WHERE giocatore = %s AND al IS NULL;",
                    (giocatore,))

        cur.execute("UPDATE squadra SET nome = %s WHERE nome = %s;", (nome_squadra + " Rinominata", nome_squadra))

        aperte = _aperta(cur, giocatore)
        assert len(aperte) == 1
        assert aperte[0]["squadra"] == nome_squadra + " Rinominata"
        assert aperte[0]["dal"].date() == date(2025, 1, 1)


class TestPromozione:
    def _primavera(self, cur, squadra):
        cur.execute(
            """SELECT id FROM giocatore
               WHERE detentore_cartellino = %s AND tipo_contratto = 'Primavera' LIMIT 1;""",
            (squadra,))
        riga = cur.fetchone()
        if not riga:
            pytest.skip(f"Nessun giocatore in Primavera per {squadra}.")
        return riga["id"]

    def test_promozione_apre_una_permanenza_nuova(self, app, cur, db_isolato, schema, nome_squadra):
        giocatore = self._primavera(cur, nome_squadra)
        db_isolato.commit()

        c = app.test_client()
        with c.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=nome_squadra, username="test")
        c.post(f"/rosa/user_primavera/{nome_squadra}", data={"id_giocatore_da_promuovere": giocatore})

        storico = _storico(cur, giocatore)
        assert len([r for r in storico if r["al"] is not None and r["squadra"] == nome_squadra]) >= 1
        aperte = _aperta(cur, giocatore)
        assert len(aperte) == 1
        assert aperte[0]["squadra"] == nome_squadra
        assert aperte[0]["fonte"] == "promozione"
        assert aperte[0]["dal"] is not None

    def test_altri_cambi_di_contratto_non_toccano_lo_storico(self, cur, schema, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        prima = _storico(cur, giocatore)

        cur.execute("UPDATE giocatore SET tipo_contratto = 'Hold' WHERE id = %s;", (giocatore,))

        assert _storico(cur, giocatore) == prima


class TestPaginaAdmin:
    def _senza_data(self, cur, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        cur.execute(
            "UPDATE giocatore_storico SET dal = NULL, fonte = NULL WHERE giocatore = %s AND al IS NULL RETURNING id;",
            (giocatore,))
        return cur.fetchone()["id"]

    def test_la_pagina_mostra_i_mancanti(self, app, cur, db_isolato, schema, nome_squadra):
        id_riga = self._senza_data(cur, nome_squadra)
        db_isolato.commit()

        risposta = _client_admin(app).get("/admin/arrivi_in_rosa")

        assert risposta.status_code == 200
        assert f'name="dal_{id_riga}"'.encode() in risposta.data

    def test_salva_la_data_inserita(self, app, cur, db_isolato, schema, nome_squadra):
        id_riga = self._senza_data(cur, nome_squadra)
        db_isolato.commit()

        _client_admin(app).post("/admin/arrivi_in_rosa", data={f"dal_{id_riga}": "2024-08-20"})

        cur.execute("SELECT dal, fonte FROM giocatore_storico WHERE id = %s;", (id_riga,))
        riga = cur.fetchone()
        assert riga["dal"].date() == date(2024, 8, 20)
        assert riga["fonte"] == "admin"

    def test_rifiuta_una_data_nel_futuro(self, app, cur, db_isolato, schema, nome_squadra):
        id_riga = self._senza_data(cur, nome_squadra)
        db_isolato.commit()
        domani = (date.today() + timedelta(days=2)).isoformat()

        _client_admin(app).post("/admin/arrivi_in_rosa", data={f"dal_{id_riga}": domani})

        cur.execute("SELECT dal FROM giocatore_storico WHERE id = %s;", (id_riga,))
        assert cur.fetchone()["dal"] is None

    def test_non_sovrascrive_una_data_gia_nota(self, app, cur, db_isolato, schema, nome_squadra):
        giocatore = _giocatore_in_rosa(cur, nome_squadra)
        cur.execute(
            "UPDATE giocatore_storico SET dal = '2025-03-01' WHERE giocatore = %s AND al IS NULL RETURNING id;",
            (giocatore,))
        id_riga = cur.fetchone()["id"]
        db_isolato.commit()

        _client_admin(app).post("/admin/arrivi_in_rosa", data={f"dal_{id_riga}": "2024-08-20"})

        cur.execute("SELECT dal FROM giocatore_storico WHERE id = %s;", (id_riga,))
        assert cur.fetchone()["dal"].date() == date(2025, 3, 1)
