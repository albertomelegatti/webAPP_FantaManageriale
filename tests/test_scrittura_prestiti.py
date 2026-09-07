"""
Percorsi di scrittura dei prestiti: attivazione e riscatto.

Contiene anche i test sull'atomicita' dello spostamento crediti, corretta nella
Fase 8a: erano marcati xfail finche' il difetto esisteva, ora sono test normali.
"""

import pytest

pytestmark = pytest.mark.db


def _due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono almeno due squadre.")
    return righe[0]["nome"], righe[1]["nome"]


def _giocatore_di(cur, squadra):
    cur.execute(
        """SELECT id FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto NOT IN ('Fanta-Prestito', 'Primavera')
           LIMIT 1;""",
        (squadra,),
    )
    riga = cur.fetchone()
    if not riga:
        pytest.skip(f"Nessun giocatore prestabile per {squadra}.")
    return riga["id"]


def _crea_prestito(cur, giocatore, prestante, ricevente, stato="in_attesa",
                   costo=0, tipo="secco", riscatto=0):
    cur.execute(
        """INSERT INTO prestito (giocatore, squadra_prestante, squadra_ricevente, stato,
                                 data_inizio, data_fine, costo_prestito, tipo_prestito,
                                 crediti_riscatto, note)
           VALUES (%s, %s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome',
                   (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '300 days', %s, %s, %s, '')
           RETURNING id;""",
        (giocatore, prestante, ricevente, stato, costo, tipo, riscatto),
    )
    return cur.fetchone()["id"]


def _crediti(cur, squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (squadra,))
    return cur.fetchone()["crediti"]


def _client(app, squadra):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=False, nome_squadra=squadra, username="test")
    return c


class TestAttivazionePrestito:
    def test_il_giocatore_passa_alla_squadra_ricevente(self, app, cur, db_isolato, gate_aperto):
        prestante, ricevente = _due_squadre(cur)
        giocatore = _giocatore_di(cur, prestante)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        id_prestito = _crea_prestito(cur, giocatore, prestante, ricevente)
        db_isolato.commit()

        _client(app, ricevente).post(f"/prestiti/prestiti/{ricevente}",
                                     data={"accetta_prestito": id_prestito})

        cur.execute("SELECT squadra_att, tipo_contratto FROM giocatore WHERE id = %s;", (giocatore,))
        dopo = cur.fetchone()
        assert dopo["squadra_att"] == ricevente
        assert dopo["tipo_contratto"] == "Fanta-Prestito"

        cur.execute("SELECT stato FROM prestito WHERE id = %s;", (id_prestito,))
        assert cur.fetchone()["stato"] == "in_corso"

    def test_il_costo_del_prestito_si_sposta_dal_ricevente_al_prestante(
        self, app, cur, db_isolato, gate_aperto
    ):
        prestante, ricevente = _due_squadre(cur)
        giocatore = _giocatore_di(cur, prestante)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        id_prestito = _crea_prestito(cur, giocatore, prestante, ricevente, costo=35)
        db_isolato.commit()

        _client(app, ricevente).post(f"/prestiti/prestiti/{ricevente}",
                                     data={"accetta_prestito": id_prestito})

        assert _crediti(cur, ricevente) == 300 - 35
        assert _crediti(cur, prestante) == 300 + 35
        assert _crediti(cur, ricevente) + _crediti(cur, prestante) == 600

    def test_il_rifiuto_non_muove_nulla(self, app, cur, db_isolato, gate_aperto):
        prestante, ricevente = _due_squadre(cur)
        giocatore = _giocatore_di(cur, prestante)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        id_prestito = _crea_prestito(cur, giocatore, prestante, ricevente, costo=35)
        db_isolato.commit()

        _client(app, ricevente).post(f"/prestiti/prestiti/{ricevente}",
                                     data={"rifiuta_prestito": id_prestito})

        cur.execute("SELECT stato FROM prestito WHERE id = %s;", (id_prestito,))
        assert cur.fetchone()["stato"] == "rifiutato"
        cur.execute("SELECT squadra_att FROM giocatore WHERE id = %s;", (giocatore,))
        assert cur.fetchone()["squadra_att"] == prestante
        assert _crediti(cur, ricevente) == 300


class TestAtomicitaSpostamentoCrediti:
    """Lo spostamento dei crediti deve stare nella stessa transazione del resto.

    Prima della Fase 8a, sposta_crediti() chiamava conn.commit() al proprio
    interno, committando cosi' la transazione del CHIAMANTE. In attiva_prestito
    veniva invocata poco prima del commit finale: se qualcosa falliva fra le due,
    i crediti risultavano gia' spostati mentre il prestito non era stato
    attivato. Soldi mossi per un'operazione mai avvenuta.

    Il guasto va iniettato esattamente in quella finestra, cioe' al momento del
    commit. Iniettarlo dopo non proverebbe nulla: a commit avvenuto l'operazione
    e' conclusa e i crediti DEVONO essere spostati.
    """

    def test_se_il_commit_fallisce_i_crediti_non_restano_spostati(
        self, app, cur, db_isolato, gate_aperto, monkeypatch
    ):
        prestante, ricevente = _due_squadre(cur)
        giocatore = _giocatore_di(cur, prestante)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        id_prestito = _crea_prestito(cur, giocatore, prestante, ricevente, costo=40)
        db_isolato.commit()

        # Da qui in avanti il commit fallisce: e' il punto in cui, con il vecchio
        # codice, i crediti erano gia' stati committati per conto proprio.
        commit_originale = type(db_isolato).commit
        esplodi = {"attivo": False}

        def commit_che_fallisce(self):
            if esplodi["attivo"]:
                raise RuntimeError("commit fallito, simulato")
            return commit_originale(self)

        monkeypatch.setattr(type(db_isolato), "commit", commit_che_fallisce)
        esplodi["attivo"] = True

        _client(app, ricevente).post(f"/prestiti/prestiti/{ricevente}",
                                     data={"accetta_prestito": id_prestito})

        esplodi["attivo"] = False
        monkeypatch.undo()

        assert _crediti(cur, ricevente) == 300, "i crediti si sono mossi nonostante il fallimento"
        assert _crediti(cur, prestante) == 300

        cur.execute("SELECT stato FROM prestito WHERE id = %s;", (id_prestito,))
        assert cur.fetchone()["stato"] == "in_attesa", "il prestito non doveva risultare attivato"

    def test_a_operazione_riuscita_i_crediti_si_muovono(
        self, app, cur, db_isolato, gate_aperto
    ):
        """Il contrappeso del test sopra: senza questo, un codice che non sposta
        mai i crediti passerebbe comunque."""
        prestante, ricevente = _due_squadre(cur)
        giocatore = _giocatore_di(cur, prestante)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        id_prestito = _crea_prestito(cur, giocatore, prestante, ricevente, costo=40)
        db_isolato.commit()

        _client(app, ricevente).post(f"/prestiti/prestiti/{ricevente}",
                                     data={"accetta_prestito": id_prestito})

        assert _crediti(cur, ricevente) == 260
        assert _crediti(cur, prestante) == 340
