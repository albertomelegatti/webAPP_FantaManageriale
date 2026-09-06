"""
Test di app/core/logging.py e app/core/errori.py.

Nessun database: sono moduli puri. Il test che conta davvero è
`test_lo_stack_trace_finisce_nei_log`: è la ragione per cui i print sono stati
sostituiti, non lo stile.
"""

import logging

import pytest

from app.core.errori import (CreditiInsufficienti, ErroreDominio,
                             OperazioneNonPermessa, RisorsaNonTrovata,
                             SezioneChiusa, SlotEsauriti,
                             SlotPrestitiEsauriti, StatoNonPiuValido)
from app.core.logging import configura_logging, get_logger


class TestErroriDominio:
    def test_messaggio_di_default(self):
        assert CreditiInsufficienti().messaggio_utente == CreditiInsufficienti.messaggio_default

    def test_messaggio_personalizzato_ha_la_precedenza(self):
        e = CreditiInsufficienti("❌ Ti servono 12 crediti.")
        assert e.messaggio_utente == "❌ Ti servono 12 crediti."
        assert str(e) == "❌ Ti servono 12 crediti."

    @pytest.mark.parametrize("classe", [
        CreditiInsufficienti, SlotEsauriti, SlotPrestitiEsauriti,
        RisorsaNonTrovata, OperazioneNonPermessa, StatoNonPiuValido, SezioneChiusa,
    ])
    def test_tutte_derivano_da_errore_dominio(self, classe):
        assert issubclass(classe, ErroreDominio)
        assert isinstance(classe(), Exception)

    def test_ogni_sottoclasse_ha_un_messaggio_proprio(self):
        """Se una sottoclasse ereditasse il messaggio generico, l'utente non
        saprebbe cosa e' andato storto."""
        for classe in (CreditiInsufficienti, SlotEsauriti, SlotPrestitiEsauriti,
                       RisorsaNonTrovata, OperazioneNonPermessa, StatoNonPiuValido,
                       SezioneChiusa):
            assert classe.messaggio_default != ErroreDominio.messaggio_default

    def test_catturabile_come_errore_dominio(self):
        with pytest.raises(ErroreDominio):
            raise SlotEsauriti()


class TestLogging:
    def test_configurazione_idempotente(self):
        """create_app gira piu' volte nei test: senza idempotenza ogni riga di
        log verrebbe stampata una volta per configurazione."""
        configura_logging()
        prima = len(logging.getLogger().handlers)
        configura_logging()
        configura_logging()
        assert len(logging.getLogger().handlers) == prima

    def test_get_logger_usa_il_nome_del_modulo(self):
        assert get_logger("app.blueprints.aste").name == "app.blueprints.aste"

    def test_werkzeug_silenziato(self):
        """gunicorn logga gia' le richieste HTTP: senza questo comparirebbero due volte."""
        configura_logging()
        assert logging.getLogger("werkzeug").level == logging.WARNING

    def test_lo_stack_trace_finisce_nei_log(self, caplog):
        """Il motivo per cui i print sono stati sostituiti: print(e) stampa solo
        il messaggio e butta via il traceback, quindi dai log di produzione non
        si risale mai al punto in cui l'errore e' nato."""
        logger = get_logger("app.test")
        with caplog.at_level(logging.ERROR):
            try:
                raise ValueError("dettaglio che deve sopravvivere")
            except ValueError:
                logger.exception("operazione fallita")

        registrazione = caplog.records[-1]
        assert registrazione.exc_info is not None
        assert "ValueError" in caplog.text
        assert "dettaglio che deve sopravvivere" in caplog.text


class TestHandlerErroreDominio:
    def test_un_errore_di_dominio_diventa_un_redirect_non_un_500(self, app):
        """Registrato in create_app: la route puo' sollevare e l'utente vede il
        messaggio, non una pagina di errore."""
        @app.route("/__prova_errore_dominio")
        def _prova():
            raise CreditiInsufficienti("❌ Crediti insufficienti per il test.")

        # TESTING=True fa ri-sollevare le eccezioni: qui vogliamo l'handler.
        app.config["TESTING"] = False
        try:
            risposta = app.test_client().get("/__prova_errore_dominio")
            assert risposta.status_code == 302
        finally:
            app.config["TESTING"] = True
