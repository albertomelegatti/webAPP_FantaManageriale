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
