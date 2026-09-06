"""
Percorsi di scrittura della rosa: taglio di un giocatore.

Sono i percorsi che muovono crediti e slot, cioe' quelli in cui un errore costa
davvero, e finora erano gli unici senza copertura: la suite esercitava solo GET.
Le Fasi 5 e 6 riscrivono proprio questo codice, quindi questi test sono la rete.

Ogni test gira dentro una transazione annullata alla fine (fixture db_isolato):
le route scrivono e committano davvero, ma il database non conserva nulla.
"""

import math

import pytest

pytestmark = pytest.mark.db


def _giocatore_tagliabile(cur, nome_squadra):
    cur.execute(
        """
        SELECT id, nome, quot_att_mantra
        FROM giocatore
        WHERE detentore_cartellino = %s AND tipo_contratto <> 'Primavera'
          AND quot_att_mantra IS NOT NULL
        ORDER BY quot_att_mantra
        LIMIT 1;
        """,
        (nome_squadra,),
    )
    riga = cur.fetchone()
    if not riga:
        pytest.skip(f"Nessun giocatore tagliabile per {nome_squadra}.")
    return riga


def _crediti(cur, nome_squadra):
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    return cur.fetchone()["crediti"]


class TestTaglioGiocatore:
    def test_il_taglio_svincola_e_addebita_meta_quotazione_arrotondata_per_eccesso(
        self, client_squadra, cur, nome_squadra
    ):
        giocatore = _giocatore_tagliabile(cur, nome_squadra)
        costo_atteso = math.ceil(giocatore["quot_att_mantra"] / 2)
        crediti_prima = _crediti(cur, nome_squadra)

        risposta = client_squadra.post(
            f"/rosa/user_tagli/{nome_squadra}",
            data={"id_giocatore_da_tagliare": giocatore["id"]},
        )
        assert risposta.status_code == 302

        cur.execute(
            "SELECT squadra_att, detentore_cartellino, tipo_contratto FROM giocatore WHERE id = %s;",
            (giocatore["id"],),
        )
        dopo = cur.fetchone()
        assert dopo["squadra_att"] == "Svincolato"
        assert dopo["detentore_cartellino"] == "Svincolato"
        assert dopo["tipo_contratto"] == "Svincolato"

        assert _crediti(cur, nome_squadra) == crediti_prima - costo_atteso

    def test_senza_crediti_sufficienti_il_taglio_non_avviene(
        self, client_squadra, cur, db_isolato, nome_squadra
    ):
        """Il controllo sui crediti e' l'unica cosa che impedisce a una squadra
        di andare in negativo: va verificato che regga."""
        giocatore = _giocatore_tagliabile(cur, nome_squadra)
        costo = math.ceil(giocatore["quot_att_mantra"] / 2)

        # Lascio alla squadra meno crediti del necessario
        cur.execute("UPDATE squadra SET crediti = %s WHERE nome = %s;",
                    (max(costo - 1, 0), nome_squadra))
        db_isolato.commit()

        client_squadra.post(
            f"/rosa/user_tagli/{nome_squadra}",
            data={"id_giocatore_da_tagliare": giocatore["id"]},
        )

        cur.execute("SELECT squadra_att FROM giocatore WHERE id = %s;", (giocatore["id"],))
        assert cur.fetchone()["squadra_att"] == nome_squadra, "il giocatore non doveva essere svincolato"
        assert _crediti(cur, nome_squadra) == max(costo - 1, 0), "i crediti non dovevano cambiare"

    def test_il_giocatore_tagliato_esce_dalla_vetrina(
        self, client_squadra, cur, db_isolato, nome_squadra
    ):
        giocatore = _giocatore_tagliabile(cur, nome_squadra)
        cur.execute(
            """INSERT INTO vetrina (id_giocatore, stato, data_inserimento)
               VALUES (%s, 'cedibile', NOW() AT TIME ZONE 'Europe/Rome')
               ON CONFLICT (id_giocatore) DO NOTHING;""",
            (giocatore["id"],),
        )
        cur.execute("UPDATE squadra SET crediti = 500 WHERE nome = %s;", (nome_squadra,))
        db_isolato.commit()

        client_squadra.post(
            f"/rosa/user_tagli/{nome_squadra}",
            data={"id_giocatore_da_tagliare": giocatore["id"]},
        )

        cur.execute("SELECT 1 FROM vetrina WHERE id_giocatore = %s;", (giocatore["id"],))
        assert cur.fetchone() is None, "il giocatore svincolato doveva uscire dalla vetrina"

    def test_una_richiesta_senza_giocatore_non_cambia_nulla(
        self, client_squadra, cur, nome_squadra
    ):
        crediti_prima = _crediti(cur, nome_squadra)
        risposta = client_squadra.post(f"/rosa/user_tagli/{nome_squadra}", data={})
        assert risposta.status_code == 200
        assert _crediti(cur, nome_squadra) == crediti_prima
