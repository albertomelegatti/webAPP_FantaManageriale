"""
Storico draft: quali pick compaiono in pagina e in che ordine.

In tabella ci sono gia' le pick degli anni futuri, ancora senza giocatore:
la pagina deve mostrare solo i draft svolti, dall'anno piu' recente e, dentro
l'anno, nell'ordine di chiamata. La squadra mostrata e' chi deteneva la pick,
che dopo uno scambio non e' quella originale.
"""

from datetime import date

import pytest

pytestmark = pytest.mark.db


def _inserisci(cur, id_pick, anno, giro, numero, detentore, originale=None, id_giocatore=None):
    cur.execute(
        """INSERT INTO draft (id, anno, giro, numero, detentore_att, detentore_originale, id_giocatore_scelto)
           VALUES (%s, %s, %s, %s, %s, %s, %s);""",
        (id_pick, date(anno, 1, 1), giro, numero, detentore, originale or detentore, id_giocatore))


@pytest.fixture
def draft_pulito(cur, db_isolato):
    """Svuota il draft per la durata del test: si verifica su righe note."""
    cur.execute("DELETE FROM draft;")
    db_isolato.commit()
    return cur


@pytest.fixture
def due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    return righe[0]["nome"], righe[1]["nome"]


@pytest.fixture
def tre_giocatori(cur):
    cur.execute("SELECT id FROM giocatore ORDER BY id LIMIT 3;")
    righe = cur.fetchall()
    if len(righe) < 3:
        pytest.skip("Servono tre giocatori.")
    return [r["id"] for r in righe]


def _storico(cur):
    from app.repositories import draft as draft_repo
    return draft_repo.storico(cur)


class TestStorico:
    def test_esclude_le_pick_non_ancora_usate(self, draft_pulito, db_isolato, due_squadre, tre_giocatori):
        prima, _ = due_squadre
        _inserisci(draft_pulito, 900001, 2026, 1, 1, prima, id_giocatore=tre_giocatori[0])
        _inserisci(draft_pulito, 900002, 2027, 1, None, prima)
        db_isolato.commit()

        assert [r["anno"] for r in _storico(draft_pulito)] == ["2026"]

    def test_anno_piu_recente_prima_poi_ordine_di_chiamata(
        self, draft_pulito, db_isolato, due_squadre, tre_giocatori
    ):
        prima, seconda = due_squadre
        g1, g2, g3 = tre_giocatori
        _inserisci(draft_pulito, 900001, 2025, 1, 1, prima, id_giocatore=g1)
        _inserisci(draft_pulito, 900002, 2026, 2, 12, prima, id_giocatore=g2)
        _inserisci(draft_pulito, 900003, 2026, 1, 3, seconda, id_giocatore=g3)
        db_isolato.commit()

        assert [(r["anno"], r["numero"]) for r in _storico(draft_pulito)] == [
            ("2026", 3), ("2026", 12), ("2025", 1)]

    def test_la_squadra_e_chi_deteneva_la_pick(self, draft_pulito, db_isolato, due_squadre, tre_giocatori):
        prima, seconda = due_squadre
        _inserisci(draft_pulito, 900001, 2026, 1, 1, seconda, originale=prima,
                   id_giocatore=tre_giocatori[0])
        db_isolato.commit()

        assert _storico(draft_pulito)[0]["squadra"] == seconda


class TestPagina:
    def test_la_pagina_mostra_le_scelte(self, app, draft_pulito, db_isolato, due_squadre, tre_giocatori):
        prima, _ = due_squadre
        _inserisci(draft_pulito, 900001, 2026, 1, 1, prima, id_giocatore=tre_giocatori[0])
        db_isolato.commit()

        risposta = app.test_client().get("/draft")
        assert risposta.status_code == 200
        assert prima in risposta.get_data(as_text=True)

    def test_un_draft_vuoto_non_rompe_la_pagina(self, app, draft_pulito):
        risposta = app.test_client().get("/draft")
        assert risposta.status_code == 200
        assert "Nessun draft registrato" in risposta.get_data(as_text=True)
