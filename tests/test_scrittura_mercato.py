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
