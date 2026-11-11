"""Accrediti annuali: premi dell'albo d'oro e rendite degli stadi, una volta per stagione.

Servono la tabella accrediti_annuali (CronJob/accrediti_annuali_schema.sql). Come gli
altri test di scrittura girano in una transazione annullata alla fine (db_isolato).
"""

import pytest

pytestmark = pytest.mark.db

STAGIONE = "30-31"


@pytest.fixture
def telegram(monkeypatch):
    """Registra le comunicazioni che partirebbero, senza inviarle."""
    from app import telegram_utils
    inviate = []
    monkeypatch.setattr(telegram_utils, "accredito_competizione",
                        lambda stagione, competizione, accrediti: inviate.append(("albo", stagione, competizione, list(accrediti))))
    monkeypatch.setattr(telegram_utils, "accredito_rendite_stadi",
                        lambda stagione, accrediti: inviate.append(("rendite", stagione, list(accrediti))))
    return inviate


@pytest.fixture
def albo(cur, db_isolato):
    """Una stagione di prova: Campionato (prima 100, seconda 50) e Coppa (prima 30 + 10, seconda 5)."""
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    prima, seconda = righe[0]["nome"], righe[1]["nome"]

    cur.execute("DELETE FROM accrediti_annuali WHERE stagione = %s;", (STAGIONE,))
    cur.execute("DELETE FROM albo_oro WHERE stagione = %s;", (STAGIONE,))
    for competizione, fase, squadra, pos, crediti in (
            ("Campionato", None, prima, 1, 100), ("Campionato", None, seconda, 2, 50),
            ("Coppa", "Final 4", prima, 1, 30), ("Coppa", "Girone A", prima, 1, 10),
            ("Coppa", "Girone B", seconda, 1, 5)):
        cur.execute(
            """INSERT INTO albo_oro (stagione, competizione, fase, squadra, posizione, crediti_generati)
               VALUES (%s, %s, %s, %s, %s, %s);""", (STAGIONE, competizione, fase, squadra, pos, crediti))
    db_isolato.commit()
    return prima, seconda


def _crediti(cur, squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (squadra,))
    return cur.fetchone()["crediti"]


def _admin(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=True, username="admin")
    return c


class TestServizioAlbo:
    def test_accredita_i_premi_e_registra(self, cur, albo):
        from app.services import accrediti
        prima, seconda = albo
        c1, c2 = _crediti(cur, prima), _crediti(cur, seconda)

        esito = accrediti.accredita_albo(cur, STAGIONE, "Campionato", "admin:t")

        assert esito["accrediti"] == [(prima, 100), (seconda, 50)] and esito["totale"] == 150
        assert (_crediti(cur, prima), _crediti(cur, seconda)) == (c1 + 100, c2 + 50)
        cur.execute("SELECT * FROM accrediti_annuali WHERE chiave = %s;", (f"albo_oro:{STAGIONE}:Campionato",))
        riga = cur.fetchone()
        assert (riga["squadre"], riga["totale"], riga["eseguito_da"], riga["storico"]) == (2, 150, "admin:t", False)

    def test_la_coppa_somma_i_premi_di_piu_fasi(self, cur, albo):
        from app.services import accrediti
        prima, seconda = albo
        assert accrediti.accredita_albo(cur, STAGIONE, "Coppa", "a")["accrediti"] == [(prima, 40), (seconda, 5)]

    def test_il_secondo_accredito_non_cambia_niente(self, cur, albo):
        from app.services import accrediti
        prima, seconda = albo
        accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")
        dopo = (_crediti(cur, prima), _crediti(cur, seconda))

        with pytest.raises(accrediti.GiaAccreditato, match="Già accreditato"):
            accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")

        assert (_crediti(cur, prima), _crediti(cur, seconda)) == dopo

    def test_le_competizioni_sono_indipendenti(self, cur, albo):
        from app.services import accrediti
        accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")
        accrediti.accredita_albo(cur, STAGIONE, "Coppa", "a")   # non deve fermarsi

    def test_un_accredito_fallito_si_puo_ripetere(self, cur, albo, monkeypatch):
        """Se qualcosa va storto dopo la registrazione, l'annullamento toglie anche la riga."""
        from app.repositories import squadre as squadre_repo
        from app.services import accrediti
        prima, seconda = albo
        c1 = _crediti(cur, prima)

        cur.execute("SAVEPOINT tentativo;")
        originale = squadre_repo.aggiungi_crediti
        chiamate = []

        def guasta(cur_, nome, crediti):
            chiamate.append(nome)
            if len(chiamate) == 2:
                raise RuntimeError("guasto")
            originale(cur_, nome, crediti)

        monkeypatch.setattr(squadre_repo, "aggiungi_crediti", guasta)
        with pytest.raises(RuntimeError):
            accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")
        cur.execute("ROLLBACK TO SAVEPOINT tentativo;")
        monkeypatch.setattr(squadre_repo, "aggiungi_crediti", originale)

        assert _crediti(cur, prima) == c1                      # niente a meta'
        accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")   # e si puo' rifare
        assert _crediti(cur, prima) == c1 + 100

    def test_una_stagione_archiviata_e_gia_accreditata(self, cur, albo):
        """Le righe storiche (segnate dalla migrazione) bloccano un secondo accredito."""
        from app.services import accrediti
        cur.execute("""INSERT INTO accrediti_annuali (chiave, tipo, stagione, competizione, eseguito_da, storico)
                       VALUES (%s, 'albo_oro', %s, 'Campionato', 'storico', true);""",
                    (f"albo_oro:{STAGIONE}:Campionato", STAGIONE))
        with pytest.raises(accrediti.GiaAccreditato):
            accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")

    def test_senza_crediti_non_registra_niente(self, cur, albo):
        from app.core.errori import ErroreDominio
        from app.services import accrediti
        cur.execute("UPDATE albo_oro SET crediti_generati = 0 WHERE stagione = %s;", (STAGIONE,))
        with pytest.raises(ErroreDominio, match="nessun credito"):
            accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")
        cur.execute("SELECT COUNT(*) AS n FROM accrediti_annuali WHERE stagione = %s;", (STAGIONE,))
        assert cur.fetchone()["n"] == 0

    def test_competizione_non_valida(self, cur, albo):
        from app.core.errori import ErroreDominio
        from app.services import accrediti
        with pytest.raises(ErroreDominio, match="non valida"):
            accrediti.accredita_albo(cur, STAGIONE, "Supercoppa", "a")

    def test_senza_registro_non_si_accredita(self, cur, albo, monkeypatch):
        from app.core.errori import ErroreDominio
        from app.repositories import accrediti as registro
        from app.services import accrediti
        prima, _ = albo
        c1 = _crediti(cur, prima)
        monkeypatch.setattr(registro, "disponibile", lambda cur_: False)
        with pytest.raises(ErroreDominio, match="accrediti_annuali_schema"):
            accrediti.accredita_albo(cur, STAGIONE, "Campionato", "a")
        assert _crediti(cur, prima) == c1


class TestRouteAlbo:
    def _post(self, c, competizione="Campionato"):
        return c.post("/admin/albo_oro/accredita", data={"stagione": STAGIONE, "competizione": competizione})

    def test_accredita_e_manda_telegram(self, app, cur, albo, telegram):
        prima, seconda = albo
        c1 = _crediti(cur, prima)
        self._post(_admin(app))
        assert _crediti(cur, prima) == c1 + 100
        assert telegram == [("albo", STAGIONE, "Campionato", [(prima, 100), (seconda, 50)])]

    def test_il_secondo_invio_non_accredita_ne_manda_telegram(self, app, cur, albo, telegram):
        prima, _ = albo
        c = _admin(app)
        self._post(c)
        dopo = _crediti(cur, prima)
        self._post(c)                                   # anche da un'altra sessione
        self._post(_admin(app))
        assert _crediti(cur, prima) == dopo
        assert len(telegram) == 1

    def test_una_squadra_non_puo_accreditare(self, app, cur, albo, telegram, client_squadra):
        prima, _ = albo
        c1 = _crediti(cur, prima)
        self._post(client_squadra)
        assert _crediti(cur, prima) == c1 and telegram == []

    def test_la_pagina_mostra_il_pulsante_e_poi_lo_stato(self, app, cur, albo, telegram):
        c = _admin(app)
        prima_pagina = c.get(f"/admin/albo_oro?stagione={STAGIONE}").get_data(as_text=True)
        assert "Accredita 150 crediti a 2 squadre" in prima_pagina

        self._post(c)
        dopo = c.get(f"/admin/albo_oro?stagione={STAGIONE}").get_data(as_text=True)
        assert "Accredita 150 crediti" not in dopo
        assert "Già accreditato" in dopo
        assert "Accredita 45 crediti a 2 squadre" in dopo      # la Coppa e' ancora da fare

    def test_singolare_con_una_squadra_e_un_credito(self, app, cur, db_isolato, albo):
        cur.execute("DELETE FROM albo_oro WHERE stagione = %s AND competizione = 'Campionato' AND posizione = 2;", (STAGIONE,))
        cur.execute("UPDATE albo_oro SET crediti_generati = 1 WHERE stagione = %s AND competizione = 'Campionato';", (STAGIONE,))
        db_isolato.commit()
        pagina = _admin(app).get(f"/admin/albo_oro?stagione={STAGIONE}").get_data(as_text=True)
        assert "Accredita 1 credito a 1 squadra" in pagina
        assert "1 squadra · 1 credito" in pagina
        assert "1 crediti" not in pagina and "1 squadre" not in pagina

    def test_avviso_se_manca_il_registro(self, app, albo, monkeypatch):
        from app.repositories import accrediti as registro
        monkeypatch.setattr(registro, "disponibile", lambda cur_: False)
        pagina = _admin(app).get(f"/admin/albo_oro?stagione={STAGIONE}").get_data(as_text=True)
        assert "accrediti_annuali_schema.sql" in pagina


class TestRendite:
    def _gettone(self, app):
        c = _admin(app)
        c.get("/admin/stadi")                       # la pagina emette il gettone monouso
        with c.session_transaction() as s:
            return c, s["token_rendite"]

    def _libera(self, cur, db_isolato):
        from app.core.tempo import oggi
        from app.domini.accrediti import stagione_corrente
        cur.execute("DELETE FROM accrediti_annuali WHERE chiave = %s;",
                    (f"rendite_stadi:{stagione_corrente(oggi())}",))
        db_isolato.commit()

    def test_accredita_una_volta_e_manda_telegram(self, app, cur, db_isolato, telegram):
        self._libera(cur, db_isolato)
        c, token = self._gettone(app)
        c.post("/admin/stadi/accredita_rendite", data={"token": token})
        assert len(telegram) == 1 and telegram[0][0] == "rendite"

    def test_ricaricare_la_pagina_non_permette_di_rifarlo(self, app, cur, db_isolato, telegram):
        """Il gettone di sessione fermava solo il doppio clic: il registro ferma anche questo."""
        self._libera(cur, db_isolato)
        c, token = self._gettone(app)
        c.post("/admin/stadi/accredita_rendite", data={"token": token})
        crediti = {r["nome"]: r["crediti"] for r in _tutti(cur)}

        c2, nuovo_token = self._gettone(app)        # pagina ricaricata: gettone nuovo e valido
        c2.post("/admin/stadi/accredita_rendite", data={"token": nuovo_token})

        assert {r["nome"]: r["crediti"] for r in _tutti(cur)} == crediti
        assert len(telegram) == 1

    def test_la_pagina_mostra_lo_stato(self, app, cur, db_isolato, telegram):
        self._libera(cur, db_isolato)
        c, token = self._gettone(app)
        assert "Accredita rendite a tutte le squadre" in c.get("/admin/stadi").get_data(as_text=True)

        c.get("/admin/stadi")
        with c.session_transaction() as s:
            token = s["token_rendite"]
        c.post("/admin/stadi/accredita_rendite", data={"token": token})
        pagina = c.get("/admin/stadi").get_data(as_text=True)
        assert "già accreditate" in pagina
        assert "Accredita rendite a tutte le squadre" not in pagina

    def test_senza_registro_non_accredita(self, app, cur, db_isolato, telegram, monkeypatch):
        from app.repositories import accrediti as registro
        crediti = {r["nome"]: r["crediti"] for r in _tutti(cur)}
        c, token = self._gettone(app)
        monkeypatch.setattr(registro, "disponibile", lambda cur_: False)
        c.post("/admin/stadi/accredita_rendite", data={"token": token})
        assert {r["nome"]: r["crediti"] for r in _tutti(cur)} == crediti and telegram == []


def _tutti(cur):
    cur.execute("SELECT nome, crediti FROM squadra;")
    return cur.fetchall()
