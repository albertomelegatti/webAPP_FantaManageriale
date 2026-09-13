"""
Il legame fra un movimento e le squadre coinvolte.

Prima era una ricerca per sottostringa sul testo dell'evento: funzionava solo
perche' nessuna squadra ha un nome sottostringa di un'altra, e non era
indicizzabile. La colonna `squadre` la popola chi scrive il movimento, non chi
lo legge - questi test verificano che il collegamento regga in entrambe le
direzioni.
"""

import pytest

from app.repositories import movimenti as movimenti_repo

pytestmark = pytest.mark.db


class TestSalvaERitrova:
    def test_un_movimento_di_una_sola_squadra_si_ritrova(self, cur, db_isolato):
        movimenti_repo.salva(cur, "Evento di prova a una squadra", ["Sborada"], "99-00")
        db_isolato.commit()

        trovati = [m["evento"] for m in movimenti_repo.per_squadra(cur, "Sborada")]
        assert "Evento di prova a una squadra" in trovati

    def test_un_movimento_di_due_squadre_si_ritrova_da_entrambe(self, cur, db_isolato):
        movimenti_repo.salva(cur, "Scambio di prova", ["Sborada", "FC Pontos"], "99-00")
        db_isolato.commit()

        assert "Scambio di prova" in [m["evento"] for m in movimenti_repo.per_squadra(cur, "Sborada")]
        assert "Scambio di prova" in [m["evento"] for m in movimenti_repo.per_squadra(cur, "FC Pontos")]

    def test_non_compare_per_una_squadra_non_coinvolta(self, cur, db_isolato):
        movimenti_repo.salva(cur, "Evento che non la riguarda", ["Sborada"], "99-00")
        db_isolato.commit()

        assert "Evento che non la riguarda" not in [m["evento"] for m in movimenti_repo.per_squadra(cur, "FC Pontos")]

    def test_compare_nell_elenco_completo(self, cur, db_isolato):
        movimenti_repo.salva(cur, "Evento visibile a tutti", ["Sborada"], "99-00")
        db_isolato.commit()

        assert "Evento visibile a tutti" in [m["evento"] for m in movimenti_repo.tutti(cur)]

    def test_un_nome_sottostringa_di_un_altro_non_si_confonde(self, cur, db_isolato):
        """Il difetto che la colonna sostituisce: con l'ILIKE, una squadra il
        cui nome fosse sottostringa di un'altra si sarebbe vista attribuire
        anche i movimenti dell'altra. Con l'uguaglianza esatta nell'array, no.
        """
        movimenti_repo.salva(cur, "Evento della squadra grande", ["FC Pontos"], "99-00")
        db_isolato.commit()

        assert "Evento della squadra grande" not in [m["evento"] for m in movimenti_repo.per_squadra(cur, "Pontos")]


class TestEscludeLeAste:
    def test_un_movimento_asta_non_compare_nell_elenco(self, cur, db_isolato):
        movimenti_repo.salva(cur, "🏷️ ASTA: qualcosa di irrilevante", ["Sborada"], "99-00")
        db_isolato.commit()

        assert "🏷️ ASTA: qualcosa di irrilevante" not in [m["evento"] for m in movimenti_repo.tutti(cur)]
        assert "🏷️ ASTA: qualcosa di irrilevante" not in [m["evento"] for m in movimenti_repo.per_squadra(cur, "Sborada")]
