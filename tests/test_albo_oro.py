"""
Albo d'oro: l'ordinamento con cui i piazzamenti compaiono in pagina.

E' la parte non ovvia del repository, ed e' logica di presentazione espressa in
SQL: la stagione piu' recente in cima, il Campionato prima della Coppa, e dentro
la Coppa le fasi finali prima dei gironi. Quest'ultima regola esiste perche'
`fase` e' testo libero: un ordinamento alfabetico metterebbe "Finale" dopo
"Girone A", che e' il contrario dell'ordine in cui si giocano.
"""

import pytest

pytestmark = pytest.mark.db


def _inserisci(cur, stagione, competizione, fase, squadra, posizione, crediti=0):
    cur.execute(
        """INSERT INTO albo_oro (stagione, competizione, fase, squadra, posizione, crediti_generati)
           VALUES (%s, %s, %s, %s, %s, %s);""",
        (stagione, competizione, fase, squadra, posizione, crediti))


@pytest.fixture
def albo_pulito(cur, db_isolato):
    """Svuota l'albo per la durata del test: l'ordinamento si verifica su righe
    note, non su quelle reali che possono cambiare."""
    cur.execute("DELETE FROM albo_oro;")
    db_isolato.commit()
    return cur


@pytest.fixture
def due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    return righe[0]["nome"], righe[1]["nome"]


def _ordine(cur):
    from app.repositories import albo_oro as albo_oro_repo
    return [(r["stagione"], r["competizione"], r["fase"], r["posizione"])
            for r in albo_oro_repo.leggi(cur)]


class TestOrdinamento:
    def test_le_stagioni_piu_recenti_vengono_prima(self, albo_pulito, db_isolato, due_squadre):
        prima, _ = due_squadre
        _inserisci(albo_pulito, "23-24", "Campionato", None, prima, 1)
        _inserisci(albo_pulito, "25-26", "Campionato", None, prima, 1)
        _inserisci(albo_pulito, "24-25", "Campionato", None, prima, 1)
        db_isolato.commit()

        assert [r[0] for r in _ordine(albo_pulito)] == ["25-26", "24-25", "23-24"]

    def test_il_campionato_viene_prima_della_coppa(self, albo_pulito, db_isolato, due_squadre):
        prima, _ = due_squadre
        _inserisci(albo_pulito, "25-26", "Coppa", "Finale", prima, 1)
        _inserisci(albo_pulito, "25-26", "Campionato", None, prima, 1)
        db_isolato.commit()

        assert [r[1] for r in _ordine(albo_pulito)] == ["Campionato", "Coppa"]

    def test_le_fasi_finali_precedono_i_gironi(self, albo_pulito, db_isolato, due_squadre):
        prima, seconda = due_squadre
        _inserisci(albo_pulito, "25-26", "Coppa", "Girone A", prima, 1)
        _inserisci(albo_pulito, "25-26", "Coppa", "Final 4", seconda, 1)
        db_isolato.commit()

        assert [r[2] for r in _ordine(albo_pulito)] == ["Final 4", "Girone A"]

    def test_le_fasi_finali_precedono_anche_i_nomi_che_le_anticiperebbero(
        self, albo_pulito, db_isolato, due_squadre
    ):
        """Il caso che l'ordinamento alfabetico da solo sbaglierebbe.

        Con i nomi usati oggi ("Final 4", "Girone A") l'alfabetico basterebbe,
        perche' F viene prima di G. Una fase chiamata "Eliminatorie" invece
        precederebbe alfabeticamente la finale, pur giocandosi prima: e' per
        questo che il repository forza le fasi "Final%" in cima invece di
        affidarsi all'alfabeto.
        """
        prima, seconda = due_squadre
        _inserisci(albo_pulito, "25-26", "Coppa", "Eliminatorie", prima, 1)
        _inserisci(albo_pulito, "25-26", "Coppa", "Final 4", seconda, 1)
        db_isolato.commit()

        assert [r[2] for r in _ordine(albo_pulito)] == ["Final 4", "Eliminatorie"]

    def test_il_campionato_senza_fase_precede_le_fasi_della_coppa(
        self, albo_pulito, db_isolato, due_squadre
    ):
        """fase e' NULL per il Campionato: NULLS FIRST lo tiene in cima."""
        prima, seconda = due_squadre
        _inserisci(albo_pulito, "25-26", "Campionato", None, prima, 2)
        _inserisci(albo_pulito, "25-26", "Campionato", None, seconda, 1)
        db_isolato.commit()

        assert [r[3] for r in _ordine(albo_pulito)] == [1, 2], \
            "dentro la stessa fase conta la posizione"


class TestPalmares:
    def test_una_squadra_senza_titoli_ha_zero_e_zero(self, albo_pulito, due_squadre):
        from app.repositories import albo_oro as albo_oro_repo
        prima, _ = due_squadre
        assert albo_oro_repo.palmares(albo_pulito, prima) == {"campionati": 0, "coppe": 0}

    def test_conta_i_primi_posti_in_campionato(self, albo_pulito, db_isolato, due_squadre):
        from app.repositories import albo_oro as albo_oro_repo
        prima, _ = due_squadre
        _inserisci(albo_pulito, "23-24", "Campionato", None, prima, 1)
        _inserisci(albo_pulito, "24-25", "Campionato", None, prima, 2)
        _inserisci(albo_pulito, "25-26", "Campionato", None, prima, 1)
        db_isolato.commit()

        assert albo_oro_repo.palmares(albo_pulito, prima)["campionati"] == 2

    def test_conta_solo_i_primi_posti_nella_fase_finale_di_coppa(
        self, albo_pulito, db_isolato, due_squadre
    ):
        """Il primo posto in un girone non e' un titolo: la Coppa si vince in finale."""
        from app.repositories import albo_oro as albo_oro_repo
        prima, _ = due_squadre
        _inserisci(albo_pulito, "24-25", "Coppa", "Girone A", prima, 1)
        _inserisci(albo_pulito, "25-26", "Coppa", "Finale", prima, 1)
        db_isolato.commit()

        assert albo_oro_repo.palmares(albo_pulito, prima)["coppe"] == 1

    def test_non_conta_i_titoli_delle_altre_squadre(self, albo_pulito, db_isolato, due_squadre):
        from app.repositories import albo_oro as albo_oro_repo
        prima, seconda = due_squadre
        _inserisci(albo_pulito, "25-26", "Campionato", None, seconda, 1)
        db_isolato.commit()

        assert albo_oro_repo.palmares(albo_pulito, prima) == {"campionati": 0, "coppe": 0}


class TestOrdinamentoCompleto:
    def test_l_ordinamento_completo(self, albo_pulito, db_isolato, due_squadre):
        """Tutte le regole insieme, nell'ordine in cui si applicano."""
        prima, seconda = due_squadre
        _inserisci(albo_pulito, "24-25", "Campionato", None, prima, 1)
        _inserisci(albo_pulito, "25-26", "Coppa", "Girone A", prima, 1)
        _inserisci(albo_pulito, "25-26", "Coppa", "Finale", seconda, 2)
        _inserisci(albo_pulito, "25-26", "Coppa", "Finale", prima, 1)
        _inserisci(albo_pulito, "25-26", "Campionato", None, seconda, 1)
        db_isolato.commit()

        assert _ordine(albo_pulito) == [
            ("25-26", "Campionato", None, 1),
            ("25-26", "Coppa", "Finale", 1),
            ("25-26", "Coppa", "Finale", 2),
            ("25-26", "Coppa", "Girone A", 1),
            ("24-25", "Campionato", None, 1),
        ]


class TestPagina:
    def test_la_pagina_mostra_i_piazzamenti(self, app, albo_pulito, db_isolato, due_squadre):
        prima, _ = due_squadre
        _inserisci(albo_pulito, "25-26", "Campionato", None, prima, 1, crediti=50)
        db_isolato.commit()

        risposta = app.test_client().get("/albo_oro")
        assert risposta.status_code == 200
        assert prima in risposta.get_data(as_text=True)

    def test_un_albo_vuoto_non_rompe_la_pagina(self, app, albo_pulito):
        assert app.test_client().get("/albo_oro").status_code == 200
