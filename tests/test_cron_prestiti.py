"""
Il job di fine prestito (CronJob/cron_job_prestiti.sql).

La funzione viene ricreata dal file del repository dentro la transazione del
test: CREATE OR REPLACE FUNCTION e' transazionale, quindi alla fine torna quella
che c'era sul database di sviluppo.
"""

from pathlib import Path

import pytest

pytestmark = pytest.mark.db

SQL_FUNZIONE = Path(__file__).resolve().parent.parent / "CronJob" / "cron_job_prestiti.sql"

# data_fine come la salva l'app: ora italiana "nominale" alle 23:59:59
OGGI = "(NOW() AT TIME ZONE 'Europe/Rome')::date + TIME '23:59:59'"
DOMANI = "(NOW() AT TIME ZONE 'Europe/Rome')::date + 1 + TIME '23:59:59'"


@pytest.fixture
def squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    prestante, ricevente = righe[0]["nome"], righe[1]["nome"]
    cur.execute("UPDATE squadra SET crediti = 300 WHERE nome IN (%s, %s);", (prestante, ricevente))
    cur.execute(SQL_FUNZIONE.read_text(encoding="utf-8"))
    return prestante, ricevente


def _giocatori(cur, squadra, quanti):
    cur.execute(
        """SELECT id FROM giocatore WHERE squadra_att = %s
           AND tipo_contratto NOT IN ('Fanta-Prestito', 'Primavera') ORDER BY id LIMIT %s;""",
        (squadra, quanti))
    ids = [r["id"] for r in cur.fetchall()]
    if len(ids) < quanti:
        pytest.skip(f"Servono {quanti} giocatori di {squadra}.")
    return ids


def _presta(cur, giocatore, prestante, ricevente, tipo, stato, data_fine=OGGI, riscatto=45):
    cur.execute(
        """UPDATE giocatore SET squadra_att = %s, detentore_cartellino = %s,
                                tipo_contratto = 'Fanta-Prestito' WHERE id = %s;""",
        (ricevente, prestante, giocatore))
    cur.execute(
        f"""INSERT INTO prestito (giocatore, squadra_prestante, squadra_ricevente, stato,
                                  data_inizio, data_fine, costo_prestito, tipo_prestito,
                                  crediti_riscatto, note)
            VALUES (%s, %s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome', {data_fine},
                    0, %s, %s, '')
            RETURNING id;""",
        (giocatore, prestante, ricevente, stato, tipo, riscatto))
    return cur.fetchone()["id"]


def _esegui_job(cur):
    cur.execute("SELECT public.processa_prestiti_conclusi();")


def _giocatore(cur, giocatore):
    cur.execute(
        "SELECT squadra_att, detentore_cartellino, tipo_contratto FROM giocatore WHERE id = %s;",
        (giocatore,))
    return cur.fetchone()


def _stato(cur, id_prestito):
    cur.execute("SELECT stato FROM prestito WHERE id = %s;", (id_prestito,))
    return cur.fetchone()["stato"]


def _crediti(cur, squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (squadra,))
    return cur.fetchone()["crediti"]


class TestRiscattoAFinePrestito:
    @pytest.mark.parametrize("tipo, stato", [
        ("diritto_di_riscatto", "riscattato"),
        ("obbligo_di_riscatto", "in_corso"),
    ])
    def test_a_scadenza_il_riscatto_diventa_effettivo(self, cur, squadre, tipo, stato):
        prestante, ricevente = squadre
        [giocatore] = _giocatori(cur, prestante, 1)
        id_prestito = _presta(cur, giocatore, prestante, ricevente, tipo, stato)

        _esegui_job(cur)

        assert _giocatore(cur, giocatore) == {
            "squadra_att": ricevente, "detentore_cartellino": ricevente,
            "tipo_contratto": "Indeterminato"}
        assert _crediti(cur, ricevente) == 300 - 45
        assert _crediti(cur, prestante) == 300 + 45
        assert _stato(cur, id_prestito) == "terminato"

    def test_prima_della_scadenza_resta_un_fanta_prestito(self, cur, squadre):
        prestante, ricevente = squadre
        [giocatore] = _giocatori(cur, prestante, 1)
        id_prestito = _presta(cur, giocatore, prestante, ricevente,
                              "diritto_di_riscatto", "riscattato", data_fine=DOMANI)

        _esegui_job(cur)

        assert _giocatore(cur, giocatore)["tipo_contratto"] == "Fanta-Prestito"
        assert _giocatore(cur, giocatore)["detentore_cartellino"] == prestante
        assert _crediti(cur, ricevente) == 300
        assert _stato(cur, id_prestito) == "riscattato"

    def test_piu_riscatti_della_stessa_squadra_si_pagano_tutti(self, cur, squadre):
        prestante, ricevente = squadre
        primo, secondo = _giocatori(cur, prestante, 2)
        _presta(cur, primo, prestante, ricevente, "diritto_di_riscatto", "riscattato", riscatto=30)
        _presta(cur, secondo, prestante, ricevente, "obbligo_di_riscatto", "in_corso", riscatto=20)

        _esegui_job(cur)

        assert _crediti(cur, ricevente) == 300 - 50
        assert _crediti(cur, prestante) == 300 + 50


class TestRientroAFinePrestito:
    @pytest.mark.parametrize("tipo, stato", [
        ("secco", "in_corso"),
        ("diritto_di_riscatto", "in_corso"),
        ("secco", "richiesta_di_terminazione"),
    ])
    def test_a_scadenza_il_giocatore_torna_alla_prestante(self, cur, squadre, tipo, stato):
        prestante, ricevente = squadre
        [giocatore] = _giocatori(cur, prestante, 1)
        id_prestito = _presta(cur, giocatore, prestante, ricevente, tipo, stato)

        _esegui_job(cur)

        assert _giocatore(cur, giocatore) == {
            "squadra_att": prestante, "detentore_cartellino": prestante,
            "tipo_contratto": "Indeterminato"}
        assert _crediti(cur, ricevente) == 300
        assert _stato(cur, id_prestito) == "terminato"
