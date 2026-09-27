"""
Blocco dei tagli: un giocatore della prima squadra si puo' tagliare solo dopo
4 mesi dal suo arrivo in rosa (giocatore_storico.dal). Il taglio dalla
Primavera non ha questo vincolo.
"""

import math
from datetime import date, timedelta

import pytest

from app.core.tempo import aggiungi_mesi, oggi


class TestAggiungiMesi:
    @pytest.mark.parametrize("data, mesi, attesa", [
        (date(2026, 5, 15), 4, date(2026, 9, 15)),
        (date(2026, 10, 31), 4, date(2027, 2, 28)),
        (date(2027, 10, 31), 4, date(2028, 2, 29)),
        (date(2026, 11, 30), 4, date(2027, 3, 30)),
        (date(2026, 9, 1), 0, date(2026, 9, 1)),
    ])
    def test_somma_i_mesi_restando_nel_mese_giusto(self, data, mesi, attesa):
        assert aggiungi_mesi(data, mesi) == attesa


def _giocatore(cur, squadra, primavera=False):
    cur.execute(
        f"""SELECT id, nome, quot_att_mantra FROM giocatore
            WHERE detentore_cartellino = %s AND tipo_contratto {'=' if primavera else '<>'} 'Primavera'
              AND quot_att_mantra IS NOT NULL
            ORDER BY quot_att_mantra LIMIT 1;""",
        (squadra,))
    riga = cur.fetchone()
    if not riga:
        pytest.skip(f"Nessun giocatore adatto per {squadra}.")
    return riga


def _arrivato(cur, id_giocatore, quando):
    cur.execute("UPDATE giocatore_storico SET dal = %s WHERE giocatore = %s AND al IS NULL;",
                (quando, id_giocatore))


def _crediti(cur, squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (squadra,))
    return cur.fetchone()["crediti"]


def _detentore(cur, id_giocatore):
    cur.execute("SELECT detentore_cartellino FROM giocatore WHERE id = %s;", (id_giocatore,))
    return cur.fetchone()["detentore_cartellino"]


@pytest.mark.db
class TestBloccoTagli:
    def test_arrivato_da_poco_non_si_taglia(self, client_squadra, cur, db_isolato, nome_squadra):
        giocatore = _giocatore(cur, nome_squadra)
        _arrivato(cur, giocatore["id"], oggi() - timedelta(days=30))
        cur.execute("UPDATE squadra SET crediti = 500 WHERE nome = %s;", (nome_squadra,))
        db_isolato.commit()

        client_squadra.post(f"/rosa/user_tagli/{nome_squadra}",
                            data={"id_giocatore_da_tagliare": giocatore["id"]})

        assert _detentore(cur, giocatore["id"]) == nome_squadra
        assert _crediti(cur, nome_squadra) == 500

    def test_dopo_quattro_mesi_si_taglia(self, client_squadra, cur, db_isolato, nome_squadra):
        giocatore = _giocatore(cur, nome_squadra)
        _arrivato(cur, giocatore["id"], aggiungi_mesi(oggi(), -4))
        cur.execute("UPDATE squadra SET crediti = 500 WHERE nome = %s;", (nome_squadra,))
        db_isolato.commit()

        client_squadra.post(f"/rosa/user_tagli/{nome_squadra}",
                            data={"id_giocatore_da_tagliare": giocatore["id"]})

        assert _detentore(cur, giocatore["id"]) == "Svincolato"
        assert _crediti(cur, nome_squadra) == 500 - math.ceil(giocatore["quot_att_mantra"] / 2)

    def test_senza_data_di_arrivo_si_taglia(self, client_squadra, cur, db_isolato, nome_squadra):
        """Non sapendo da quanto e' in rosa, non c'e' motivo per bloccarlo."""
        giocatore = _giocatore(cur, nome_squadra)
        _arrivato(cur, giocatore["id"], None)
        cur.execute("UPDATE squadra SET crediti = 500 WHERE nome = %s;", (nome_squadra,))
        db_isolato.commit()

        client_squadra.post(f"/rosa/user_tagli/{nome_squadra}",
                            data={"id_giocatore_da_tagliare": giocatore["id"]})

        assert _detentore(cur, giocatore["id"]) == "Svincolato"

    def test_la_pagina_mostra_il_lucchetto(self, client_squadra, cur, db_isolato, nome_squadra):
        giocatore = _giocatore(cur, nome_squadra)
        arrivo = oggi() - timedelta(days=10)
        _arrivato(cur, giocatore["id"], arrivo)
        db_isolato.commit()

        risposta = client_squadra.get(f"/rosa/user_tagli/{nome_squadra}")

        assert risposta.status_code == 200
        sblocco = aggiungi_mesi(arrivo, 4).strftime("%d/%m/%Y")
        assert f"tagliabile dal {sblocco}".encode() in risposta.data

    def test_la_primavera_si_taglia_anche_se_appena_arrivata(self, client_squadra, cur, db_isolato, nome_squadra):
        giocatore = _giocatore(cur, nome_squadra, primavera=True)
        _arrivato(cur, giocatore["id"], oggi())
        db_isolato.commit()

        client_squadra.post(f"/rosa/user_primavera/{nome_squadra}",
                            data={"id_giocatore_da_tagliare": giocatore["id"]})

        assert _detentore(cur, giocatore["id"]) == "Svincolato"
