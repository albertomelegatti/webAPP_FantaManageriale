"""
Il numero di query di una pagina non deve dipendere da quante righe mostra.

E' la garanzia che una N+1 non rientri di soppiatto: il conteggio assoluto puo'
cambiare legittimamente in futuro, la sua *crescita con i dati* no.

Prima della Fase 6a la pagina mercato costava 27 query e 23 checkout dal pool
per 17 scambi, perche' ogni riga ne richiedeva cinque e la risoluzione dei nomi
prelevava una connessione propria mentre la route ne teneva gia' una.
"""

import contextlib

import pytest

pytestmark = pytest.mark.db


@contextlib.contextmanager
def conta_query(monkeypatch):
    """Conta le esecuzioni di query e i prelievi di connessioni dal pool."""
    import psycopg2.extras

    from app.core import db

    conteggi = {"query": 0, "checkout": 0}
    esegui_originale = psycopg2.extras.RealDictCursor.execute
    preleva_originale = db.get_connection

    def esegui(self, query, vars=None):
        conteggi["query"] += 1
        return esegui_originale(self, query, vars)

    def preleva():
        conteggi["checkout"] += 1
        return preleva_originale()

    monkeypatch.setattr(psycopg2.extras.RealDictCursor, "execute", esegui)
    monkeypatch.setattr(db, "get_connection", preleva)
    yield conteggi


def _crea_scambi(cur, proponente, destinataria, quanti):
    for _ in range(quanti):
        cur.execute(
            """INSERT INTO scambio (squadra_proponente, squadra_destinataria,
                                    giocatori_offerti, giocatori_richiesti,
                                    crediti_offerti, crediti_richiesti,
                                    messaggio, stato, data_proposta)
               VALUES (%s, %s, %s, %s, 0, 0, 'test', 'in_attesa',
                       NOW() AT TIME ZONE 'Europe/Rome');""",
            (proponente, destinataria, [], []))


class TestPaginaMercato:
    def test_le_query_non_crescono_con_il_numero_di_scambi(
        self, app, cur, db_isolato, gate_aperto, monkeypatch, nome_squadra
    ):
        cur.execute("SELECT nome FROM squadra WHERE nome <> %s AND nome <> 'Svincolato' LIMIT 1;",
                    (nome_squadra,))
        altra = cur.fetchone()["nome"]

        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=nome_squadra, username="test")

        with conta_query(monkeypatch) as base:
            client.get(f"/mercato/mercato/{nome_squadra}")
        query_iniziali = base["query"]

        _crea_scambi(cur, nome_squadra, altra, 25)
        db_isolato.commit()

        with conta_query(monkeypatch) as dopo:
            risposta = client.get(f"/mercato/mercato/{nome_squadra}")

        assert risposta.status_code == 200
        assert dopo["query"] == query_iniziali, (
            f"25 scambi in piu' hanno aggiunto {dopo['query'] - query_iniziali} query: "
            "il costo della pagina cresce con i dati")

    def test_una_sola_connessione_per_richiesta(
        self, app, cur, db_isolato, gate_aperto, monkeypatch, nome_squadra
    ):
        """La risoluzione dei nomi prelevava una seconda connessione dal pool
        mentre la route ne teneva gia' una, due volte per riga di scambio."""
        client = app.test_client()
        with client.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=nome_squadra, username="test")

        with conta_query(monkeypatch) as conteggi:
            client.get(f"/mercato/mercato/{nome_squadra}")

        # una per il gate del mercato, una per la pagina
        assert conteggi["checkout"] <= 2, (
            f"{conteggi['checkout']} connessioni prelevate per una sola richiesta")


class TestPagineRosa:
    """Entrambe le pagine chiedevano, per ogni giocatore, se avesse gia' una
    richiesta di modifica contratto aperta: una query per riga dentro il ciclo
    di rendering."""

    def _client(self, app, squadra):
        c = app.test_client()
        with c.session_transaction() as s:
            s.update(logged_in=True, is_admin=False, nome_squadra=squadra, username="test")
        return c

    def _sposta_giocatori(self, cur, verso, quanti, contratto):
        """Assegna altri giocatori alla squadra, per far crescere la pagina."""
        cur.execute(
            """UPDATE giocatore SET detentore_cartellino = %s, squadra_att = %s,
                                    tipo_contratto = %s
               WHERE id IN (SELECT id FROM giocatore
                            WHERE squadra_att = 'Svincolato' LIMIT %s);""",
            (verso, verso, contratto, quanti))

    def test_i_tagli_non_crescono_con_la_rosa(
        self, app, cur, db_isolato, monkeypatch, nome_squadra
    ):
        client = self._client(app, nome_squadra)
        with conta_query(monkeypatch) as base:
            client.get(f"/rosa/user_tagli/{nome_squadra}")
        iniziali = base["query"]

        self._sposta_giocatori(cur, nome_squadra, 20, "Indeterminato")
        db_isolato.commit()

        with conta_query(monkeypatch) as dopo:
            risposta = client.get(f"/rosa/user_tagli/{nome_squadra}")

        assert risposta.status_code == 200
        assert dopo["query"] == iniziali, (
            f"20 giocatori in piu' hanno aggiunto {dopo['query'] - iniziali} query")

    def test_la_primavera_non_cresce_con_i_giocatori(
        self, app, cur, db_isolato, monkeypatch, nome_squadra
    ):
        client = self._client(app, nome_squadra)
        with conta_query(monkeypatch) as base:
            client.get(f"/rosa/user_primavera/{nome_squadra}")
        iniziali = base["query"]

        self._sposta_giocatori(cur, nome_squadra, 15, "Primavera")
        db_isolato.commit()

        with conta_query(monkeypatch) as dopo:
            risposta = client.get(f"/rosa/user_primavera/{nome_squadra}")

        assert risposta.status_code == 200
        assert dopo["query"] == iniziali, (
            f"15 giocatori in piu' hanno aggiunto {dopo['query'] - iniziali} query")


class TestDashboardSquadra:
    def test_la_dashboard_non_supera_sei_query(
        self, app, cur, db_isolato, monkeypatch, nome_squadra
    ):
        """Era a dieci, poi cinque; il palmares in testata ne ha aggiunta una
        sesta (tabella diversa, non c'era modo di unirla alle altre). Il tetto
        resta esplicito perche' su questo database il tempo della pagina e'
        quasi interamente il numero di viaggi di rete: una query in piu' sono
        cinquanta millisecondi in piu'."""
        client = app.test_client()
        with conta_query(monkeypatch) as conteggi:
            risposta = client.get(f"/squadra/{nome_squadra}")

        assert risposta.status_code == 200
        assert conteggi["query"] <= 6, f"{conteggi['query']} query per la dashboard"

    def test_le_query_non_crescono_con_la_rosa(
        self, app, cur, db_isolato, monkeypatch, nome_squadra
    ):
        client = app.test_client()
        with conta_query(monkeypatch) as base:
            client.get(f"/squadra/{nome_squadra}")
        iniziali = base["query"]

        cur.execute(
            """UPDATE giocatore SET squadra_att = %s, detentore_cartellino = %s,
                                    tipo_contratto = 'Indeterminato'
               WHERE id IN (SELECT id FROM giocatore WHERE squadra_att = 'Svincolato' LIMIT 20);""",
            (nome_squadra, nome_squadra))
        db_isolato.commit()

        with conta_query(monkeypatch) as dopo:
            client.get(f"/squadra/{nome_squadra}")

        assert dopo["query"] == iniziali, \
            f"20 giocatori in piu' hanno aggiunto {dopo['query'] - iniziali} query"
