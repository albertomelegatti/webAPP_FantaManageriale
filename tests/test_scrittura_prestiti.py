"""
Percorsi di scrittura dei prestiti: attivazione e riscatto.

Contiene anche la documentazione eseguibile di un difetto noto di atomicita',
marcato xfail(strict=True): oggi fallisce come previsto, e nel momento in cui
la Fase 8 lo corregge il test passa e la marcatura strict segnala che va tolta.
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
    """Difetto noto, non ancora corretto.

    app/queries.py sposta_crediti() chiama conn.commit() al proprio interno,
    committando cosi' la transazione del CHIAMANTE. In attiva_prestito viene
    invocata prima del commit finale: se qualcosa fallisce fra le due, i crediti
    risultano gia' spostati mentre il prestito non e' stato attivato.

    Il test descrive il comportamento corretto e oggi fallisce. E' marcato
    xfail(strict=True), quindi quando la Fase 8 rendera' sposta_crediti
    partecipante alla transazione invece che padrona, il test passera' e la
    marcatura strict fara' rumore per ricordare di toglierla.
    """

    @pytest.mark.xfail(
        strict=True,
        reason="sposta_crediti committa la transazione del chiamante: correzione prevista in Fase 8",
    )
    def test_se_l_attivazione_fallisce_i_crediti_non_devono_essersi_mossi(
        self, app, cur, db_isolato, gate_aperto, monkeypatch
    ):
        from app.blueprints import prestiti as modulo

        prestante, ricevente = _due_squadre(cur)
        giocatore = _giocatore_di(cur, prestante)
        cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
        id_prestito = _crea_prestito(cur, giocatore, prestante, ricevente, costo=40)
        db_isolato.commit()

        # Fa fallire l'operazione DOPO lo spostamento dei crediti e PRIMA del
        # commit finale: e' la finestra in cui i due passi si separano.
        def esplode(*args, **kwargs):
            raise RuntimeError("errore simulato dopo lo spostamento dei crediti")

        monkeypatch.setattr(modulo.telegram_utils, "prestito_risposta", esplode)

        _client(app, ricevente).post(f"/prestiti/prestiti/{ricevente}",
                                     data={"accetta_prestito": id_prestito})

        assert _crediti(cur, ricevente) == 300, "i crediti si sono mossi nonostante il fallimento"
        assert _crediti(cur, prestante) == 300
