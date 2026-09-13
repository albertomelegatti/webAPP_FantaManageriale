"""
Le squadre dichiarate esplicitamente da chi scrive un movimento, non piu'
dedotte dal testo.

`send_message` scrive nel registro pubblico solo quando il destinatario e'
'gruppo_comunicazioni' (vedi telegram_utils.py); durante i test l'invio vero
resta disattivato dalla fixture di sessione, quindi qui si esercita
direttamente la scrittura, bypassando il filtro sull'invio.
"""

import pytest

from app import telegram_utils
from app.repositories import movimenti as movimenti_repo

pytestmark = pytest.mark.db


class TestSalvaMovimento:
    def test_scrive_le_squadre_dichiarate(self, cur, db_isolato):
        telegram_utils.salva_movimento("Messaggio di prova", ["Sborada", "FC Pontos"])

        trovati = movimenti_repo.per_squadra(cur, "Sborada")
        assert "Messaggio di prova" in [m["evento"] for m in trovati]

    def test_senza_squadre_non_si_ritrova_da_nessuna(self, cur, db_isolato):
        telegram_utils.salva_movimento("Messaggio senza squadre", [])

        assert "Messaggio senza squadre" not in [m["evento"] for m in movimenti_repo.per_squadra(cur, "Sborada")]
        assert "Messaggio senza squadre" in [m["evento"] for m in movimenti_repo.tutti(cur)]


class TestSendMessagePassaLeSquadre:
    """Verifica il collegamento fra send_message e salva_movimento, senza
    passare dal database: qui interessa solo che il parametro arrivi."""

    @pytest.fixture
    def spia(self, monkeypatch, app):
        chiamate = []
        monkeypatch.setattr(telegram_utils, "salva_movimento",
                            lambda testo, squadre: chiamate.append((testo, squadre)))
        monkeypatch.setattr(telegram_utils, "NOTIFICATIONS_ENABLED", True)
        monkeypatch.setattr(telegram_utils, "_enqueue_telegram_message", lambda chat_id, testo: None)
        with app.app_context():
            app.config["SQUADRE_TELEGRAM_IDS"] = {"gruppo_comunicazioni": [123]}
            yield chiamate

    def test_le_squadre_dichiarate_arrivano_a_salva_movimento(self, spia):
        telegram_utils.send_message(nome_squadra="gruppo_comunicazioni", text_to_send="Prova",
                                    squadre_evento=["Sborada", "FC Pontos"])
        assert spia == [("Prova", ["Sborada", "FC Pontos"])]

    def test_senza_squadre_evento_arriva_una_lista_vuota(self, spia):
        telegram_utils.send_message(nome_squadra="gruppo_comunicazioni", text_to_send="Prova")
        assert spia == [("Prova", [])]

    def test_verso_una_squadra_singola_non_scrive_il_movimento(self, spia):
        telegram_utils.send_message(nome_squadra="Sborada", text_to_send="Messaggio privato")
        assert spia == []
