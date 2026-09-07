"""
Percorsi di scrittura rimasti scoperti dopo la Fase 5b: primavera, riscatto di
un prestito e accettazione admin di una modifica contratto.

Sono i rami in cui la conversione delle firme dei repository da `conn` a `cur`
non era verificata da alcun test. L'analisi statica diceva che il cursore era in
scope; questi test lo dimostrano eseguendolo.
"""

import pytest

pytestmark = pytest.mark.db


def _crediti(cur, squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (squadra,))
    return cur.fetchone()["crediti"]


def _client(app, squadra, admin=False):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=admin, nome_squadra=squadra, username="admin" if admin else "test")
    return c


def _crea_primavera(cur, squadra):
    cur.execute(
        """UPDATE giocatore SET squadra_att = %s, detentore_cartellino = %s,
                                tipo_contratto = 'Primavera'
           WHERE id = (SELECT id FROM giocatore WHERE squadra_att = %s
                       AND tipo_contratto <> 'Primavera' LIMIT 1)
           RETURNING id;""",
        (squadra, squadra, squadra),
    )
    riga = cur.fetchone()
    if not riga:
        pytest.skip(f"Nessun giocatore convertibile in primavera per {squadra}.")
    return riga["id"]


class TestPrimavera:
    def test_promozione_in_prima_squadra(self, app, cur, db_isolato, nome_squadra):
        giocatore = _crea_primavera(cur, nome_squadra)
        db_isolato.commit()

        _client(app, nome_squadra).post(
            f"/rosa/user_primavera/{nome_squadra}",
            data={"id_giocatore_da_promuovere": giocatore},
        )

        cur.execute("SELECT tipo_contratto FROM giocatore WHERE id = %s;", (giocatore,))
        assert cur.fetchone()["tipo_contratto"] == "Indeterminato"

    def test_taglio_dalla_primavera_e_gratuito(self, app, cur, db_isolato, nome_squadra):
        """A differenza del taglio dalla prima squadra, questo non costa crediti."""
        giocatore = _crea_primavera(cur, nome_squadra)
        cur.execute("UPDATE squadra SET crediti = 200 WHERE nome = %s;", (nome_squadra,))
        db_isolato.commit()

        _client(app, nome_squadra).post(
            f"/rosa/user_primavera/{nome_squadra}",
            data={"id_giocatore_da_tagliare": giocatore},
        )

        cur.execute("SELECT squadra_att, tipo_contratto FROM giocatore WHERE id = %s;", (giocatore,))
        dopo = cur.fetchone()
        assert dopo["squadra_att"] == "Svincolato"
        assert dopo["tipo_contratto"] == "Svincolato"
        assert _crediti(cur, nome_squadra) == 200, "il taglio dalla primavera deve essere gratuito"


class TestRiscattoPrestito:
    def test_il_riscatto_sposta_i_crediti_e_il_cartellino(self, app, cur, db_isolato):
        cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
        righe = cur.fetchall()
        if len(righe) < 2:
            pytest.skip("Servono due squadre.")
        prestante, ricevente = righe[0]["nome"], righe[1]["nome"]

        cur.execute(
            """SELECT id FROM giocatore WHERE squadra_att = %s
               AND tipo_contratto NOT IN ('Fanta-Prestito', 'Primavera') LIMIT 1;""",
            (prestante,))
        riga = cur.fetchone()
        if not riga:
            pytest.skip("Nessun giocatore disponibile.")
        giocatore = riga["id"]

        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        cur.execute(
            """UPDATE giocatore SET squadra_att = %s, detentore_cartellino = %s,
                                    tipo_contratto = 'Fanta-Prestito' WHERE id = %s;""",
            (ricevente, prestante, giocatore))
        cur.execute(
            """INSERT INTO prestito (giocatore, squadra_prestante, squadra_ricevente, stato,
                                     data_inizio, data_fine, costo_prestito, tipo_prestito,
                                     crediti_riscatto, note)
               VALUES (%s, %s, %s, 'in_corso', NOW() AT TIME ZONE 'Europe/Rome',
                       (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '300 days',
                       0, 'diritto_di_riscatto', 45, '')
               RETURNING id;""",
            (giocatore, prestante, ricevente))
        id_prestito = cur.fetchone()["id"]
        db_isolato.commit()

        _client(app, ricevente).post(
            f"/rosa/user_gestione_prestiti/{ricevente}",
            data={"riscatta_giocatore": id_prestito},
        )

        cur.execute(
            "SELECT squadra_att, detentore_cartellino, tipo_contratto FROM giocatore WHERE id = %s;",
            (giocatore,))
        dopo = cur.fetchone()
        assert dopo["squadra_att"] == ricevente
        assert dopo["detentore_cartellino"] == ricevente, "il cartellino deve passare a chi riscatta"
        assert dopo["tipo_contratto"] == "Indeterminato"

        assert _crediti(cur, ricevente) == 300 - 45
        assert _crediti(cur, prestante) == 300 + 45

        cur.execute("SELECT stato FROM prestito WHERE id = %s;", (id_prestito,))
        assert cur.fetchone()["stato"] == "terminato"


class TestModificaContrattoAdmin:
    def test_accettare_una_richiesta_di_svincolo_accredita_i_crediti(
        self, app, cur, db_isolato, nome_squadra
    ):
        cur.execute("SELECT id FROM giocatore WHERE squadra_att = %s LIMIT 1;", (nome_squadra,))
        riga = cur.fetchone()
        if not riga:
            pytest.skip("Nessun giocatore.")
        giocatore = riga["id"]

        cur.execute("UPDATE squadra SET crediti = 100 WHERE nome = %s;", (nome_squadra,))
        cur.execute(
            """INSERT INTO richiesta_modifica_contratto
                   (giocatore, contratto_richiesto, squadra_richiedente, crediti_richiesti,
                    messaggio, data, stato)
               VALUES (%s, 'Svincolato', %s, 20, 'test',
                       NOW() AT TIME ZONE 'Europe/Rome', 'in_elaborazione')
               RETURNING id;""",
            (giocatore, nome_squadra))
        id_richiesta = cur.fetchone()["id"]
        db_isolato.commit()

        _client(app, nome_squadra, admin=True).post(
            "/admin/richiesta/modifica/contratto",
            data={"accetta_richiesta": "1", "id_richiesta": id_richiesta},
        )

        cur.execute(
            "SELECT squadra_att, detentore_cartellino, tipo_contratto FROM giocatore WHERE id = %s;",
            (giocatore,))
        dopo = cur.fetchone()
        assert dopo["squadra_att"] == "Svincolato"
        assert dopo["detentore_cartellino"] == "Svincolato"

        assert _crediti(cur, nome_squadra) == 120, "i crediti richiesti vanno accreditati"

        cur.execute("SELECT stato FROM richiesta_modifica_contratto WHERE id = %s;", (id_richiesta,))
        assert cur.fetchone()["stato"] == "accettata"


class TestRichiestaModificaContratto:
    """Il percorso che crea la richiesta, rifattorizzato nella Fase 6b per
    passare dal repository invece che da una stringa SQL nel blueprint."""

    def _giocatore(self, cur, squadra):
        cur.execute(
            "SELECT id FROM giocatore WHERE detentore_cartellino = %s LIMIT 1;", (squadra,))
        riga = cur.fetchone()
        if not riga:
            pytest.skip(f"Nessun giocatore per {squadra}.")
        return riga["id"]

    def test_la_richiesta_viene_creata_con_i_dati_inviati(
        self, app, cur, db_isolato, nome_squadra
    ):
        giocatore = self._giocatore(cur, nome_squadra)
        cur.execute("DELETE FROM richiesta_modifica_contratto WHERE giocatore = %s;", (giocatore,))
        db_isolato.commit()

        risposta = _client(app, nome_squadra).post(
            f"/rosa/{nome_squadra}/richiesta_modifica_contratto/{giocatore}",
            data={"nuovo_contratto": "Hold", "crediti_richiesti": "15", "messaggio": "prova"},
        )
        assert risposta.status_code == 302

        cur.execute(
            """SELECT contratto_richiesto, squadra_richiedente, crediti_richiesti,
                      messaggio, stato
               FROM richiesta_modifica_contratto WHERE giocatore = %s;""",
            (giocatore,))
        richiesta = cur.fetchone()
        assert richiesta is not None, "la richiesta doveva essere creata"
        assert richiesta["contratto_richiesto"] == "Hold"
        assert richiesta["squadra_richiedente"] == nome_squadra
        assert richiesta["crediti_richiesti"] == 15
        assert richiesta["messaggio"] == "prova"
        assert richiesta["stato"] == "in_elaborazione"

    def test_le_varianti_dello_svincolo_azzerano_i_crediti(
        self, app, cur, db_isolato, nome_squadra
    ):
        """Retrocessione, scadenza contratto, ritorno all'estero e taglio
        gratuito sono etichette diverse dello stesso esito: diventano
        'Svincolato' con zero crediti, qualunque cifra sia stata inviata."""
        giocatore = self._giocatore(cur, nome_squadra)
        cur.execute("DELETE FROM richiesta_modifica_contratto WHERE giocatore = %s;", (giocatore,))
        db_isolato.commit()

        _client(app, nome_squadra).post(
            f"/rosa/{nome_squadra}/richiesta_modifica_contratto/{giocatore}",
            data={"nuovo_contratto": "Retrocessione", "crediti_richiesti": "99", "messaggio": ""},
        )

        cur.execute(
            """SELECT contratto_richiesto, crediti_richiesti
               FROM richiesta_modifica_contratto WHERE giocatore = %s;""", (giocatore,))
        richiesta = cur.fetchone()
        assert richiesta["contratto_richiesto"] == "Svincolato"
        assert richiesta["crediti_richiesti"] == 0, "i crediti vanno azzerati, non usati"

    def test_il_giocatore_con_richiesta_aperta_e_segnalato_nella_pagina_tagli(
        self, app, cur, db_isolato, nome_squadra
    ):
        """Il dato che prima costava una query per giocatore."""
        giocatore = self._giocatore(cur, nome_squadra)
        cur.execute("DELETE FROM richiesta_modifica_contratto WHERE giocatore = %s;", (giocatore,))
        cur.execute(
            """INSERT INTO richiesta_modifica_contratto
                   (giocatore, contratto_richiesto, squadra_richiedente, crediti_richiesti,
                    messaggio, data, stato)
               VALUES (%s, 'Hold', %s, 0, '', NOW() AT TIME ZONE 'Europe/Rome', 'in_elaborazione');""",
            (giocatore, nome_squadra))
        db_isolato.commit()

        from app.repositories import richieste as richieste_repo
        from app.services import rosa as servizio_rosa

        assert richieste_repo.id_con_richiesta_in_elaborazione(cur, [giocatore]) == {giocatore}

        elenco = servizio_rosa.giocatori_tagliabili(cur, nome_squadra)
        segnalato = {g["id"]: g["esiste_gia_una_richiesta"] for g in elenco}
        assert segnalato.get(giocatore) is True
        assert any(v is False for v in segnalato.values()), \
            "gli altri giocatori non devono risultare tutti segnalati"

    def test_elenco_vuoto_non_interroga_il_database(self, cur):
        """Il ritorno anticipato evita una query con un ANY(ARRAY[]) inutile."""
        from app.repositories import richieste as richieste_repo
        assert richieste_repo.id_con_richiesta_in_elaborazione(cur, []) == set()
        assert richieste_repo.id_con_richiesta_in_elaborazione(cur, None) == set()

    def test_una_squadra_senza_giocatori_da_un_elenco_vuoto(self, cur):
        from app.services import rosa as servizio_rosa
        assert servizio_rosa.giocatori_tagliabili(cur, "Squadra Inesistente") == []

    def test_riprova_dopo_un_conflitto_di_chiave(
        self, app, cur, db_isolato, monkeypatch, nome_squadra
    ):
        """Il recupero dal disallineamento delle sequence.

        Se un import manuale sul database ha inserito righe con id espliciti, la
        sequence resta indietro e il primo INSERT fallisce con UniqueViolation.
        Il codice riallinea e riprova, cosi' l'utente non vede l'errore.

        Il conflitto e' simulato invece che provocato davvero: forzare la
        sequence richiederebbe un setval, che NON viene annullato dal rollback e
        lascerebbe quindi una traccia sul database di sviluppo.
        """
        from psycopg2 import errors as pg_errors

        from app.blueprints import rosa as blueprint_rosa
        from app.repositories import richieste as richieste_repo

        giocatore = self._giocatore(cur, nome_squadra)
        cur.execute("DELETE FROM richiesta_modifica_contratto WHERE giocatore = %s;", (giocatore,))
        db_isolato.commit()

        crea_originale = richieste_repo.crea
        tentativi = {"n": 0}

        def crea_con_conflitto_iniziale(cursore, *args, **kwargs):
            tentativi["n"] += 1
            if tentativi["n"] == 1:
                raise pg_errors.UniqueViolation("duplicate key value violates unique constraint")
            return crea_originale(cursore, *args, **kwargs)

        monkeypatch.setattr(richieste_repo, "crea", crea_con_conflitto_iniziale)
        # il riallineamento fa setval, che sopravvivrebbe al rollback
        monkeypatch.setattr(blueprint_rosa, "resync_sequence", lambda conn, tabella: None)

        risposta = _client(app, nome_squadra).post(
            f"/rosa/{nome_squadra}/richiesta_modifica_contratto/{giocatore}",
            data={"nuovo_contratto": "Hold", "crediti_richiesti": "5", "messaggio": "retry"},
        )
        assert risposta.status_code == 302
        assert tentativi["n"] == 2, "doveva riprovare esattamente una volta"

        cur.execute(
            "SELECT messaggio FROM richiesta_modifica_contratto WHERE giocatore = %s;", (giocatore,))
        riga = cur.fetchone()
        assert riga is not None, "la richiesta doveva essere creata al secondo tentativo"
        assert riga["messaggio"] == "retry"
