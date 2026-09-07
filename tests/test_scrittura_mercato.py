"""
Percorsi di scrittura del mercato: accettazione di uno scambio.

E' l'operazione piu' complessa dell'applicazione — sposta giocatori, pick e
crediti fra due squadre, annulla gli scambi concorrenti e attiva gli eventuali
prestiti collegati — ed e' quella dove un errore ha le conseguenze peggiori.
La Fase 6 la riscrive: questi test sono il riferimento.
"""

import pytest

pytestmark = pytest.mark.db


def _due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono almeno due squadre.")
    return righe[0]["nome"], righe[1]["nome"]


def _un_giocatore_di(cur, squadra):
    cur.execute(
        """SELECT id, nome FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold')
           LIMIT 1;""",
        (squadra,),
    )
    riga = cur.fetchone()
    if not riga:
        pytest.skip(f"Nessun giocatore scambiabile per {squadra}.")
    return riga


def _crea_scambio(cur, proponente, destinataria, offerti, richiesti,
                  crediti_offerti=0, crediti_richiesti=0):
    cur.execute(
        """INSERT INTO scambio (squadra_proponente, squadra_destinataria,
                                giocatori_offerti, giocatori_richiesti,
                                crediti_offerti, crediti_richiesti,
                                messaggio, stato, data_proposta)
           VALUES (%s, %s, %s, %s, %s, %s, 'test', 'in_attesa',
                   NOW() AT TIME ZONE 'Europe/Rome')
           RETURNING id;""",
        (proponente, destinataria, offerti, richiesti, crediti_offerti, crediti_richiesti),
    )
    return cur.fetchone()["id"]


def _crediti(cur, squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (squadra,))
    return cur.fetchone()["crediti"]


class TestAccettazioneScambio:
    def test_i_giocatori_cambiano_squadra_in_entrambe_le_direzioni(
        self, app, cur, db_isolato, gate_aperto
    ):
        prop, dest = _due_squadre(cur)
        g_prop, g_dest = _un_giocatore_di(cur, prop), _un_giocatore_di(cur, dest)
        cur.execute("UPDATE squadra SET crediti = 500 WHERE nome IN (%s, %s);", (prop, dest))
        id_scambio = _crea_scambio(cur, prop, dest, [g_prop["id"]], [g_dest["id"]])
        db_isolato.commit()

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=dest, username="test")
        client.post(f"/mercato/mercato/{dest}", data={"accetta_scambio": id_scambio})

        cur.execute("SELECT id, squadra_att, detentore_cartellino FROM giocatore WHERE id = ANY(%s);",
                    ([g_prop["id"], g_dest["id"]],))
        per_id = {r["id"]: r for r in cur.fetchall()}
        assert per_id[g_prop["id"]]["squadra_att"] == dest
        assert per_id[g_prop["id"]]["detentore_cartellino"] == dest
        assert per_id[g_dest["id"]]["squadra_att"] == prop
        assert per_id[g_dest["id"]]["detentore_cartellino"] == prop

        cur.execute("SELECT stato FROM scambio WHERE id = %s;", (id_scambio,))
        assert cur.fetchone()["stato"] == "accettato"

    def test_i_crediti_si_conservano(self, app, cur, db_isolato, gate_aperto):
        """Invariante fondamentale: uno scambio sposta crediti, non li crea ne'
        li distrugge."""
        prop, dest = _due_squadre(cur)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prop, dest))
        id_scambio = _crea_scambio(cur, prop, dest, [], [], crediti_offerti=40, crediti_richiesti=15)
        db_isolato.commit()

        totale_prima = _crediti(cur, prop) + _crediti(cur, dest)

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=dest, username="test")
        client.post(f"/mercato/mercato/{dest}", data={"accetta_scambio": id_scambio})

        crediti_prop, crediti_dest = _crediti(cur, prop), _crediti(cur, dest)
        assert crediti_prop == 300 - 40 + 15
        assert crediti_dest == 300 - 15 + 40
        assert crediti_prop + crediti_dest == totale_prima

    def test_uno_scambio_gia_accettato_non_si_riesegue(self, app, cur, db_isolato, gate_aperto):
        """Senza questo controllo, un doppio invio del form sposterebbe i crediti
        due volte."""
        prop, dest = _due_squadre(cur)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prop, dest))
        id_scambio = _crea_scambio(cur, prop, dest, [], [], crediti_offerti=25)
        db_isolato.commit()

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=dest, username="test")
        client.post(f"/mercato/mercato/{dest}", data={"accetta_scambio": id_scambio})
        crediti_dopo_una_volta = (_crediti(cur, prop), _crediti(cur, dest))

        client.post(f"/mercato/mercato/{dest}", data={"accetta_scambio": id_scambio})
        assert (_crediti(cur, prop), _crediti(cur, dest)) == crediti_dopo_una_volta

    def test_senza_crediti_sufficienti_lo_scambio_viene_rifiutato(
        self, app, cur, db_isolato, gate_aperto
    ):
        prop, dest = _due_squadre(cur)
        cur.execute("UPDATE squadra SET crediti = 5 WHERE nome = %s;", (prop,))
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome = %s;", (dest,))
        id_scambio = _crea_scambio(cur, prop, dest, [], [], crediti_offerti=100)
        db_isolato.commit()

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=dest, username="test")
        client.post(f"/mercato/mercato/{dest}", data={"accetta_scambio": id_scambio})

        cur.execute("SELECT stato FROM scambio WHERE id = %s;", (id_scambio,))
        assert cur.fetchone()["stato"] == "in_attesa", "lo scambio non doveva essere accettato"
        assert _crediti(cur, prop) == 5, "i crediti non dovevano muoversi"

    def test_il_rifiuto_non_muove_crediti(self, app, cur, db_isolato, gate_aperto):
        prop, dest = _due_squadre(cur)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prop, dest))
        id_scambio = _crea_scambio(cur, prop, dest, [], [], crediti_offerti=50)
        db_isolato.commit()

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=dest, username="test")
        client.post(f"/mercato/mercato/{dest}", data={"rifiuta_scambio": id_scambio})

        cur.execute("SELECT stato FROM scambio WHERE id = %s;", (id_scambio,))
        assert cur.fetchone()["stato"] == "rifiutato"
        assert _crediti(cur, prop) == 300 and _crediti(cur, dest) == 300


class TestNuovoScambioConPrestito:
    """Copre il ramo che verifica gli slot prestito prima di creare la proposta.

    E' il percorso piu' complesso dell'applicazione (il form ha una venticinquina
    di campi) ed era scoperto: la Fase 6 lo riscrive, quindi serve una rete.
    """

    def _giocatore_di(self, cur, squadra):
        cur.execute(
            """SELECT id FROM giocatore WHERE squadra_att = %s
               AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold') LIMIT 1;""",
            (squadra,))
        riga = cur.fetchone()
        if not riga:
            pytest.skip(f"Nessun giocatore per {squadra}.")
        return riga["id"]

    def _libera_slot_prestito(self, cur, squadra):
        """Nel DB di sviluppo alcune squadre hanno gia' i due prestiti in entrata
        consentiti, quindi il limite scatterebbe a prescindere dal test."""
        cur.execute(
            """UPDATE giocatore SET tipo_contratto = 'Indeterminato',
                                    detentore_cartellino = squadra_att
               WHERE squadra_att = %s AND tipo_contratto = 'Fanta-Prestito';""",
            (squadra,))

    def _proponi(self, app, prop, dest, giocatore):
        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=prop, username="test")
        return client.post(f"/mercato/nuovo_scambio/{prop}", data={
            "squadra_destinataria": dest,
            "enable_prestito1": "on",
            "prestito1_richiesto": str(giocatore),
            "prestito1_tipo_richiesto": "Secco",
            "prestito1_data_fine_richiesta": "2027",
        })

    def test_con_slot_liberi_nascono_la_proposta_e_il_prestito_collegato(
        self, app, cur, db_isolato, gate_aperto
    ):
        prop, dest = _due_squadre(cur)
        giocatore = self._giocatore_di(cur, dest)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prop, dest))
        self._libera_slot_prestito(cur, prop)
        cur.execute("SELECT count(*) AS n FROM scambio;")
        scambi_prima = cur.fetchone()["n"]
        db_isolato.commit()

        assert self._proponi(app, prop, dest, giocatore).status_code == 302

        cur.execute("SELECT count(*) AS n FROM scambio;")
        assert cur.fetchone()["n"] == scambi_prima + 1, "la proposta doveva essere creata"

        cur.execute(
            """SELECT prestito_associato FROM scambio
               WHERE squadra_proponente = %s ORDER BY id DESC LIMIT 1;""", (prop,))
        associati = cur.fetchone()["prestito_associato"]
        assert associati, "lo scambio deve referenziare il prestito creato"

        cur.execute(
            """SELECT stato, squadra_prestante, squadra_ricevente, tipo_prestito
               FROM prestito WHERE id = ANY(%s);""", (associati,))
        prestito = cur.fetchone()
        assert prestito["stato"] == "in_attesa", "il prestito nasce sospeso, si attiva con lo scambio"
        assert prestito["squadra_prestante"] == dest
        assert prestito["squadra_ricevente"] == prop
        assert prestito["tipo_prestito"] == "secco"

    def test_con_gli_slot_prestito_pieni_la_proposta_viene_rifiutata(
        self, app, cur, db_isolato, gate_aperto
    ):
        """Il limite e' due prestiti in entrata per squadra."""
        prop, dest = _due_squadre(cur)
        giocatore = self._giocatore_di(cur, dest)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prop, dest))
        self._libera_slot_prestito(cur, prop)
        cur.execute(
            """UPDATE giocatore SET tipo_contratto = 'Fanta-Prestito'
               WHERE id IN (SELECT id FROM giocatore WHERE squadra_att = %s
                            AND tipo_contratto = 'Indeterminato' LIMIT 2);""",
            (prop,))
        cur.execute(
            "SELECT count(*) AS n FROM giocatore WHERE squadra_att = %s AND tipo_contratto = 'Fanta-Prestito';",
            (prop,))
        assert cur.fetchone()["n"] == 2, "preparazione: gli slot devono essere saturi"
        cur.execute("SELECT count(*) AS n FROM scambio;")
        scambi_prima = cur.fetchone()["n"]
        db_isolato.commit()

        self._proponi(app, prop, dest, giocatore)

        cur.execute("SELECT count(*) AS n FROM scambio;")
        assert cur.fetchone()["n"] == scambi_prima, "nessuno scambio doveva essere creato"


class TestValidazionePick:
    """Le pick devono esistere davvero: lo schema valida la forma dei dati, non
    la loro coerenza con lo stato del gioco."""

    def _proponi_con_pick(self, app, prop, dest, campo, valore):
        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=prop, username="test")
        return client.post(f"/mercato/nuovo_scambio/{prop}",
                           data={"squadra_destinataria": dest, campo: valore})

    def test_una_pick_offerta_inesistente_blocca_la_proposta(
        self, app, cur, db_isolato, gate_aperto
    ):
        prop, dest = _due_squadre(cur)
        cur.execute("SELECT count(*) AS n FROM scambio;")
        prima = cur.fetchone()["n"]
        cur.execute("SELECT COALESCE(max(id), 0) + 1000 AS inesistente FROM draft;")
        pick_inesistente = str(cur.fetchone()["inesistente"])
        db_isolato.commit()

        self._proponi_con_pick(app, prop, dest, "pick_offerta", pick_inesistente)

        cur.execute("SELECT count(*) AS n FROM scambio;")
        assert cur.fetchone()["n"] == prima, "nessuna proposta doveva essere creata"

    def test_una_pick_richiesta_inesistente_blocca_la_proposta(
        self, app, cur, db_isolato, gate_aperto
    ):
        prop, dest = _due_squadre(cur)
        cur.execute("SELECT count(*) AS n FROM scambio;")
        prima = cur.fetchone()["n"]
        cur.execute("SELECT COALESCE(max(id), 0) + 1000 AS inesistente FROM draft;")
        pick_inesistente = str(cur.fetchone()["inesistente"])
        db_isolato.commit()

        self._proponi_con_pick(app, prop, dest, "pick_richiesta", pick_inesistente)

        cur.execute("SELECT count(*) AS n FROM scambio;")
        assert cur.fetchone()["n"] == prima

    def test_una_pick_reale_viene_accettata(self, app, cur, db_isolato, gate_aperto):
        """Il contrappeso: senza, un codice che rifiuta sempre passerebbe."""
        prop, dest = _due_squadre(cur)
        cur.execute("SELECT id FROM draft LIMIT 1;")
        riga = cur.fetchone()
        if not riga:
            pytest.skip("Nessuna pick nel draft.")
        cur.execute("SELECT count(*) AS n FROM scambio;")
        prima = cur.fetchone()["n"]
        db_isolato.commit()

        self._proponi_con_pick(app, prop, dest, "pick_offerta", str(riga["id"]))

        cur.execute("SELECT count(*) AS n FROM scambio;")
        assert cur.fetchone()["n"] == prima + 1, "la proposta doveva essere creata"
