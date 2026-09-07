"""
Albo d'oro: inserimento e cancellazione di una riga dalla pagina admin.

Copre il percorso di scrittura (INSERT/DELETE su albo_oro) e il vincolo di
unicità su stagione/competizione/fase/posizione, che deve tradursi in un
messaggio d'errore e non in un 500.
"""

import pytest

pytestmark = pytest.mark.db


def _riga_albo_oro(cur, stagione, squadra):
    cur.execute(
        "SELECT id, posizione, crediti_generati FROM albo_oro "
        "WHERE stagione = %s AND squadra = %s;",
        (stagione, squadra),
    )
    return cur.fetchone()


class TestScritturaAlboOro:
    def test_aggiunta_riga_compare_in_admin_e_nella_pagina_pubblica(
        self, client_admin, cur, db_isolato, nome_squadra
    ):
        stagione = "TEST-99"
        client_admin.post("/admin/albo_oro", data={
            "stagione": stagione,
            "competizione": "Campionato",
            "fase": "",
            "squadra": nome_squadra,
            "posizione": "1",
            "crediti_generati": "42",
        })

        riga = _riga_albo_oro(cur, stagione, nome_squadra)
        assert riga is not None
        assert riga["posizione"] == 1
        assert riga["crediti_generati"] == 42

        risposta_admin = client_admin.get("/admin/albo_oro")
        assert stagione.encode() in risposta_admin.data
        assert nome_squadra.encode() in risposta_admin.data

        risposta_pubblica = client_admin.get("/albo_oro")
        assert stagione.encode() in risposta_pubblica.data

    def test_posizione_duplicata_viene_rifiutata_senza_500(
        self, client_admin, cur, db_isolato, nome_squadra
    ):
        stagione = "TEST-98"
        dati = {
            "stagione": stagione,
            "competizione": "Campionato",
            "fase": "",
            "squadra": nome_squadra,
            "posizione": "1",
            "crediti_generati": "10",
        }
        client_admin.post("/admin/albo_oro", data=dati)

        # Stessa stagione/competizione/posizione, seconda squadra: viola
        # l'unicità su (stagione, competizione, fase, posizione).
        cur.execute("SELECT nome FROM squadra WHERE nome <> %s AND nome <> 'Svincolato' LIMIT 1;",
                    (nome_squadra,))
        riga = cur.fetchone()
        if not riga:
            pytest.skip("Serve una seconda squadra per il test.")
        altra_squadra = riga["nome"]

        risposta = client_admin.post("/admin/albo_oro", data={**dati, "squadra": altra_squadra})
        assert risposta.status_code < 500

        cur.execute("SELECT COUNT(*) AS n FROM albo_oro WHERE stagione = %s;", (stagione,))
        assert cur.fetchone()["n"] == 1, "la riga duplicata non doveva essere inserita"

    def test_eliminazione_rimuove_la_riga(self, client_admin, cur, db_isolato, nome_squadra):
        stagione = "TEST-97"
        client_admin.post("/admin/albo_oro", data={
            "stagione": stagione,
            "competizione": "Campionato",
            "fase": "",
            "squadra": nome_squadra,
            "posizione": "1",
            "crediti_generati": "5",
        })
        riga = _riga_albo_oro(cur, stagione, nome_squadra)
        assert riga is not None

        client_admin.post("/admin/albo_oro", data={"elimina_id": riga["id"]})

        assert _riga_albo_oro(cur, stagione, nome_squadra) is None
