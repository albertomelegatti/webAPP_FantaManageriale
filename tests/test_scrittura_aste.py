"""
Percorsi di scrittura delle aste: iscrizione, rinuncia, rilancio, creazione.

Erano completamente scoperti, ed e' il cuore del gioco: qui si decidono i
giocatori e si impegnano i crediti. Diverse di queste operazioni usano
SELECT ... FOR UPDATE proprio perche' due squadre possono agire nello stesso
istante.

Come gli altri test di scrittura, girano dentro una transazione annullata alla
fine: le route scrivono e committano davvero, ma il database non conserva nulla.
"""

import pytest

pytestmark = pytest.mark.db


def _due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    return righe[0]["nome"], righe[1]["nome"]


def _client(app, squadra):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=False, nome_squadra=squadra, username="test")
    return c


def _crea_asta(cur, stato, partecipanti, ultima_offerta=None, vincente=None):
    cur.execute("SELECT id FROM giocatore WHERE tipo_contratto = 'Svincolato' LIMIT 1;")
    riga = cur.fetchone()
    if not riga:
        pytest.skip("Nessun giocatore svincolato.")
    cur.execute(
        """INSERT INTO asta (giocatore, squadra_vincente, ultima_offerta, tempo_fine_asta,
                             tempo_fine_mostra_interesse, stato, partecipanti, gia_elaborata)
           VALUES (%s, %s, %s,
                   (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day',
                   (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day',
                   %s, %s, FALSE)
           RETURNING id;""",
        (riga["id"], vincente, ultima_offerta, stato, partecipanti))
    return cur.fetchone()["id"]


def _partecipanti(cur, asta_id):
    cur.execute("SELECT partecipanti FROM asta WHERE id = %s;", (asta_id,))
    return cur.fetchone()["partecipanti"] or []


def _offerta(cur, asta_id):
    cur.execute("SELECT ultima_offerta, squadra_vincente FROM asta WHERE id = %s;", (asta_id,))
    riga = cur.fetchone()
    return riga["ultima_offerta"], riga["squadra_vincente"]


class TestIscrizione:
    def test_iscriversi_a_un_asta_aperta_alle_iscrizioni(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        _, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "mostra_interesse", [altra])
        db_isolato.commit()

        _client(app, nome_squadra).post(f"/aste/aste/{nome_squadra}",
                                        data={"asta_id_aste_a_cui_iscriversi": asta_id})

        assert nome_squadra in _partecipanti(cur, asta_id)

    def test_non_ci_si_iscrive_due_volte(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        """Capita che un utente invii il form due volte: la seconda non deve
        aggiungere un doppione all'elenco dei partecipanti."""
        asta_id = _crea_asta(cur, "mostra_interesse", [nome_squadra])
        db_isolato.commit()

        _client(app, nome_squadra).post(f"/aste/aste/{nome_squadra}",
                                        data={"asta_id_aste_a_cui_iscriversi": asta_id})

        assert _partecipanti(cur, asta_id).count(nome_squadra) == 1

    def test_non_ci_si_iscrive_a_un_asta_gia_avviata(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        """Le iscrizioni chiudono quando l'asta parte: chi arriva dopo resta fuori."""
        cur.execute("SELECT nome FROM squadra WHERE nome NOT IN (%s, 'Svincolato') LIMIT 1;",
                    (nome_squadra,))
        altra = cur.fetchone()["nome"]
        asta_id = _crea_asta(cur, "in_corso", [altra], ultima_offerta=5, vincente=altra)
        db_isolato.commit()

        _client(app, nome_squadra).post(f"/aste/aste/{nome_squadra}",
                                        data={"asta_id_aste_a_cui_iscriversi": asta_id})

        assert nome_squadra not in _partecipanti(cur, asta_id)


class TestRilancio:
    def test_un_rilancio_valido_aggiorna_offerta_e_squadra_in_testa(
        self, app, cur, db_isolato, gate_aperto
    ):
        io, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "in_corso", [io, altra], ultima_offerta=10, vincente=altra)
        db_isolato.commit()

        _client(app, io).post(f"/aste/singola_asta_attiva/{asta_id}/{io}",
                              data={"bottone_rilancia": "15"})

        assert _offerta(cur, asta_id) == (15, io)

    def test_un_rilancio_non_superiore_viene_rifiutato(
        self, app, cur, db_isolato, gate_aperto
    ):
        io, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "in_corso", [io, altra], ultima_offerta=10, vincente=altra)
        db_isolato.commit()

        _client(app, io).post(f"/aste/singola_asta_attiva/{asta_id}/{io}",
                              data={"bottone_rilancia": "10"})

        assert _offerta(cur, asta_id) == (10, altra), "l'offerta non doveva cambiare"

    def test_il_rilancio_rapido_somma_il_delta_all_offerta_corrente(
        self, app, cur, db_isolato, gate_aperto
    ):
        io, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "in_corso", [io, altra], ultima_offerta=20, vincente=altra)
        db_isolato.commit()

        _client(app, io).post(f"/aste/singola_asta_attiva/{asta_id}/{io}",
                              data={"delta_rilancio": "5", "offerta_attesa": "20"})

        assert _offerta(cur, asta_id) == (25, io)

    def test_il_rilancio_rapido_si_rifiuta_se_l_offerta_e_cambiata(
        self, app, cur, db_isolato, gate_aperto
    ):
        """Protezione contro il rilancio alla cieca: se qualcuno ha rilanciato
        mentre la pagina era aperta, il delta non va sommato a un valore ormai
        superato."""
        io, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "in_corso", [io, altra], ultima_offerta=30, vincente=altra)
        db_isolato.commit()

        _client(app, io).post(f"/aste/singola_asta_attiva/{asta_id}/{io}",
                              data={"delta_rilancio": "5", "offerta_attesa": "20"})

        assert _offerta(cur, asta_id) == (30, altra), "il rilancio doveva essere rifiutato"

    def test_non_si_rilancia_su_un_asta_conclusa(self, app, cur, db_isolato, gate_aperto):
        io, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "conclusa", [io, altra], ultima_offerta=40, vincente=altra)
        db_isolato.commit()

        _client(app, io).post(f"/aste/singola_asta_attiva/{asta_id}/{io}",
                              data={"bottone_rilancia": "50"})

        assert _offerta(cur, asta_id) == (40, altra)


class TestRinuncia:
    def test_rinunciare_toglie_dalla_lista_dei_partecipanti(
        self, app, cur, db_isolato, gate_aperto
    ):
        io, altra = _due_squadre(cur)
        asta_id = _crea_asta(cur, "in_corso", [io, altra], ultima_offerta=10, vincente=altra)
        db_isolato.commit()

        _client(app, io).post(f"/aste/singola_asta_attiva/{asta_id}/{io}",
                              data={"bottone_rinuncia": asta_id})

        partecipanti = _partecipanti(cur, asta_id)
        assert io not in partecipanti
        assert altra in partecipanti, "la rinuncia di una squadra non tocca le altre"


class TestCreazioneAsta:
    def test_creare_un_asta_per_un_giocatore_disponibile(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        from app.repositories import configurazione as configurazione_repo
        from app.repositories import giocatori as giocatori_repo

        disponibili = giocatori_repo.chiamabili_in_asta(
            cur, configurazione_repo.soglia_u21(cur))
        if not disponibili:
            pytest.skip("Nessun giocatore chiamabile in asta.")
        nome_giocatore = disponibili[0]["nome"]

        cur.execute("SELECT count(*) AS n FROM asta;")
        aste_prima = cur.fetchone()["n"]
        db_isolato.commit()

        _client(app, nome_squadra).post(f"/aste/nuova_asta/{nome_squadra}",
                                        data={"giocatore": nome_giocatore})

        cur.execute("SELECT count(*) AS n FROM asta;")
        assert cur.fetchone()["n"] == aste_prima + 1, "l'asta doveva essere creata"

        cur.execute(
            """SELECT a.stato, a.partecipanti FROM asta a JOIN giocatore g ON a.giocatore = g.id
               WHERE g.nome = %s ORDER BY a.id DESC LIMIT 1;""", (nome_giocatore,))
        asta = cur.fetchone()
        assert asta["stato"] == "mostra_interesse", "un'asta nuova apre le iscrizioni"
        assert nome_squadra in asta["partecipanti"], "chi la crea vi partecipa"

    def test_un_giocatore_non_disponibile_non_genera_un_asta(
        self, app, cur, db_isolato, gate_aperto, nome_squadra
    ):
        cur.execute("SELECT count(*) AS n FROM asta;")
        aste_prima = cur.fetchone()["n"]
        db_isolato.commit()

        _client(app, nome_squadra).post(f"/aste/nuova_asta/{nome_squadra}",
                                        data={"giocatore": "Giocatore Inesistente"})

        cur.execute("SELECT count(*) AS n FROM asta;")
        assert cur.fetchone()["n"] == aste_prima


class TestCreazioneGiocatoreNuovo:
    """Percorso attivo solo con ENABLE_PLAYER_CREATION: crea insieme il
    giocatore e la sua asta, per chiamare qualcuno non presente nel listone."""

    def test_un_nome_gia_esistente_viene_rifiutato(
        self, app, cur, db_isolato, gate_aperto, monkeypatch, nome_squadra
    ):
        """Il confronto ignora le maiuscole: due giocatori con lo stesso nome
        scritto diversamente sarebbero indistinguibili per gli utenti."""
        monkeypatch.setenv("ENABLE_PLAYER_CREATION", "true")
        cur.execute("SELECT nome FROM giocatore LIMIT 1;")
        gia_esistente = cur.fetchone()["nome"]
        cur.execute("SELECT count(*) AS n FROM giocatore;")
        prima = cur.fetchone()["n"]
        db_isolato.commit()

        _client(app, nome_squadra).post(
            f"/aste/nuova_asta/{nome_squadra}",
            data={"crea_nuovo": "1", "nome_nuovo": gia_esistente.upper(), "club_nuovo": "Test"})

        cur.execute("SELECT count(*) AS n FROM giocatore;")
        assert cur.fetchone()["n"] == prima, "il doppione non doveva essere creato"

    def test_un_nome_nuovo_crea_giocatore_e_asta(
        self, app, cur, db_isolato, gate_aperto, monkeypatch, nome_squadra
    ):
        monkeypatch.setenv("ENABLE_PLAYER_CREATION", "true")
        cur.execute("SELECT count(*) AS n FROM asta;")
        aste_prima = cur.fetchone()["n"]
        db_isolato.commit()

        _client(app, nome_squadra).post(
            f"/aste/nuova_asta/{nome_squadra}",
            data={"crea_nuovo": "1", "nome_nuovo": "provagiocatore inventato", "club_nuovo": "prova"})

        cur.execute("SELECT nome, club, tipo_contratto FROM giocatore WHERE LOWER(nome) = %s;",
                    ("provagiocatore inventato",))
        creato = cur.fetchone()
        assert creato is not None, "il giocatore doveva essere creato"
        assert creato["nome"] == "Provagiocatore Inventato", "il nome va normalizzato in maiuscole iniziali"
        assert creato["tipo_contratto"] == "Svincolato"

        cur.execute("SELECT count(*) AS n FROM asta;")
        assert cur.fetchone()["n"] == aste_prima + 1, "l'asta doveva partire insieme al giocatore"
