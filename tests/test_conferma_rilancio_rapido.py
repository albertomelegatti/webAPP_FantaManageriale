"""
Pop-up di conferma sul rilancio rapido dell'asta.

Il rilancio "normale" (importo libero) chiede conferma da sempre
(onsubmit="return confirm(...)"); i tre bottoni +1/+2/+5 del rilancio
rapido no, ed erano quindi l'unico modo di rilanciare un'asta con un solo
click involontario. Qui si verifica solo che il form li chieda anche lui,
non la logica di rilancio in se' (gia' coperta da test_scrittura_aste.py).
"""

import re

import pytest

pytestmark = pytest.mark.db


def _crea_asta_in_corso(cur, nome_squadra, ultima_offerta=10):
    cur.execute("SELECT id FROM giocatore WHERE tipo_contratto = 'Svincolato' LIMIT 1;")
    riga = cur.fetchone()
    if not riga:
        pytest.skip("Nessun giocatore svincolato.")
    cur.execute(
        """INSERT INTO asta (giocatore, squadra_vincente, ultima_offerta, tempo_fine_asta,
                             tempo_fine_mostra_interesse, stato, partecipanti, gia_elaborata)
           VALUES (%s, %s, %s,
                   (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day',
                   (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day',
                   'in_corso', %s, FALSE)
           RETURNING id;""",
        (riga["id"], nome_squadra, ultima_offerta, [nome_squadra]))
    return cur.fetchone()["id"]


def _form_rilancio_rapido(pagina):
    blocco = re.search(r'<form[^>]*>.*?Rilancio rapido.*?</form>', pagina, re.S)
    assert blocco, "form del rilancio rapido non trovato in pagina"
    return blocco.group(0)


class TestConfermaRilancioRapido:
    def test_il_form_chiede_conferma_come_il_rilancio_normale(
        self, client_squadra, cur, db_isolato, nome_squadra
    ):
        asta_id = _crea_asta_in_corso(cur, nome_squadra)
        db_isolato.commit()

        pagina = client_squadra.get(
            f"/aste/singola_asta_attiva/{asta_id}/{nome_squadra}").get_data(as_text=True)

        form = _form_rilancio_rapido(pagina)
        assert "onsubmit" in form and "confirm(" in form

    def test_la_conferma_riporta_l_offerta_del_bottone_cliccato(
        self, client_squadra, cur, db_isolato, nome_squadra
    ):
        """I tre bottoni condividono un solo form: il testo del pop-up deve
        dipendere da quale sia stato premuto, non essere generico."""
        asta_id = _crea_asta_in_corso(cur, nome_squadra)
        db_isolato.commit()

        pagina = client_squadra.get(
            f"/aste/singola_asta_attiva/{asta_id}/{nome_squadra}").get_data(as_text=True)

        form = _form_rilancio_rapido(pagina)
        assert "event.submitter" in form
