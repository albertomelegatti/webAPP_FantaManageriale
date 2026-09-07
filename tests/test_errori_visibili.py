"""
Un errore imprevisto non deve essere presentato come successo.

Prima ogni route intercettava le proprie eccezioni, registrava un messaggio e
proseguiva: la pagina usciva con i dati vuoti e stato 200. L'utente vedeva un
elenco senza righe invece di un errore, e nessun monitoraggio basato sui codici
di stato poteva accorgersene.

Non e' un'ipotesi: e' esattamente cosi' che un guasto al connection pool ha
servito il listone vuoto - 4 KB invece di 39 KB, stato 200 - senza che nulla lo
segnalasse. Se ne e' accorto un essere umano leggendo i log.
"""

import pytest

pytestmark = pytest.mark.db


@pytest.fixture
def app_con_handler(app):
    """TESTING=True fa ri-sollevare le eccezioni: qui vogliamo l'handler."""
    app.config["TESTING"] = False
    yield app
    app.config["TESTING"] = True


class TestErroreImprevisto:
    def test_una_query_fallita_produce_500_non_una_pagina_vuota(
        self, app_con_handler, monkeypatch, nome_squadra
    ):
        from app.blueprints import pubblico

        def esplode(*args, **kwargs):
            raise RuntimeError("database irraggiungibile, simulato")

        monkeypatch.setattr(pubblico, "connessione", esplode)

        risposta = app_con_handler.test_client().get("/listone")
        assert risposta.status_code == 500, \
            "un guasto deve dare 500, non una pagina con l'elenco vuoto"

    def test_la_pagina_di_errore_e_esplicita(self, app_con_handler, monkeypatch):
        from app.blueprints import pubblico

        monkeypatch.setattr(pubblico, "connessione",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("simulato")))
        risposta = app_con_handler.test_client().get("/listone")
        corpo = risposta.get_data(as_text=True)
        assert "andato storto" in corpo.lower(), "l'utente deve capire che c'e' stato un errore"

    def test_lo_stack_trace_finisce_nei_log(self, app_con_handler, monkeypatch, caplog):
        import logging

        from app.blueprints import pubblico

        monkeypatch.setattr(pubblico, "connessione",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dettaglio da conservare")))
        with caplog.at_level(logging.ERROR):
            app_con_handler.test_client().get("/listone")

        assert "dettaglio da conservare" in caplog.text
        assert any(r.exc_info for r in caplog.records), "manca lo stack trace"

    def test_un_errore_di_dominio_resta_un_redirect(self, app_con_handler, monkeypatch):
        """Gli errori attesi non diventano 500: sono condizioni di gioco, non guasti."""
        from app.blueprints import pubblico
        from app.core.errori import CreditiInsufficienti

        monkeypatch.setattr(pubblico, "connessione",
                            lambda *a, **k: (_ for _ in ()).throw(CreditiInsufficienti()))
        risposta = app_con_handler.test_client().get("/listone")
        assert risposta.status_code == 302


class TestAstaSenzaDataDiFine:
    """Due difetti che l'except inghiottiva, emersi appena le eccezioni hanno
    ripreso a risalire.

    Un'asta ancora in "mostra interesse" non ha ne' data di fine ne' offerta:
    la pagina di dettaglio faceva strftime su None e il template sommava un
    intero a None. Tutte e tre le aste in quello stato erano inapribili.
    """

    def test_la_pagina_si_apre_anche_senza_data_di_fine(self, app, cur, db_isolato, gate_aperto):
        cur.execute("SELECT id FROM asta WHERE giocatore IS NOT NULL LIMIT 1;")
        riga = cur.fetchone()
        if not riga:
            pytest.skip("Nessuna asta nel database.")
        asta_id = riga["id"]

        cur.execute(
            """UPDATE asta SET stato = 'mostra_interesse', tempo_fine_asta = NULL,
                               ultima_offerta = NULL WHERE id = %s;""", (asta_id,))
        db_isolato.commit()

        cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' LIMIT 1;")
        squadra = cur.fetchone()["nome"]

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=squadra, username="test")

        risposta = client.get(f"/aste/singola_asta_attiva/{asta_id}/{squadra}")
        assert risposta.status_code == 200, "un'asta senza data di fine deve restare apribile"


class TestErrore500Diretto:
    """L'handler per i 500 sollevati senza un'eccezione Python, ad esempio da
    abort(500) o da un errore del server web. Nessuna route lo fa oggi: e' una
    rete di sicurezza, ma deve funzionare quando serve."""

    def test_un_abort_500_mostra_la_pagina_di_errore(self):
        """Costruisce un'applicazione propria: Flask vieta di registrare route
        dopo la prima richiesta, e quella di sessione ne ha gia' servite."""
        from flask import abort

        from app import create_app

        applicazione = create_app()
        applicazione.config.update(TESTING=False, SESSION_COOKIE_SECURE=False)

        @applicazione.route("/__prova_500")
        def _prova():
            abort(500)

        risposta = applicazione.test_client().get("/__prova_500")
        assert risposta.status_code == 500
        assert "andato storto" in risposta.get_data(as_text=True).lower()
