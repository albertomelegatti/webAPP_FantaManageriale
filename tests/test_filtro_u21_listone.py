"""
Filtro U21 nella pagina "listone".

Il listone mostra tutti i giocatori di prima fascia; il filtro Draft (lato
client) ha due checkbox indipendenti, "Draft (U21)" e "Non-draft". Sono U21 i
giocatori nati nell'anno di soglia (general_config.u21_threshold_year) o dopo,
stessa regola delle aste. Qui verifichiamo che il server marchi correttamente
ogni giocatore e mostri il filtro solo quando la soglia e' configurata.

Lo stato viaggia nel blocco di dati in fondo alla pagina, non piu' in un
attributo della riga: le righe le disegna il browser (static/js/listone.js).
"""

import json
import re

import pytest

pytestmark = pytest.mark.db


def _crea_giocatore(cur, nome, anno_nascita, ruolo="PlaceHolderRole"):
    cur.execute(
        """INSERT INTO giocatore (
               nome, ruolo, tipo_contratto, squadra_att, detentore_cartellino,
               quot_att_mantra, costo, priorita, club, data_nascita
           )
           VALUES (%s, ARRAY[%s]::ruolo_mantra[], 'Svincolato',
                   'Svincolato', 'Svincolato', 1, 0, 1, 'Test', %s)
           RETURNING id;""",
        (nome, ruolo, f"{anno_nascita}-06-15" if anno_nascita is not None else None),
    )
    return cur.fetchone()["id"]


def _u21_di(risposta, nome):
    """Stato U21 del giocatore indicato, letto dal blocco dati della pagina."""
    corpo = risposta.get_data(as_text=True)
    dati = json.loads(re.search(r'id="datiGiocatori">(.*?)</script>', corpo, re.S).group(1))

    posizione = {campo: i for i, campo in enumerate(dati["campi"])}
    for riga in dati["righe"]:
        if riga[posizione["nome"]] == nome:
            return riga[posizione["u21"]]
    raise AssertionError(f"{nome} non trovato nel listone")


class TestFiltroU21Listone:
    def test_righe_marcate_si_no_secondo_l_anno_di_nascita(self, app, cur, db_isolato):
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        _crea_giocatore(cur, "Listone U21 Under", 2005)
        _crea_giocatore(cur, "Listone U21 Over", 1998)
        db_isolato.commit()

        risposta = app.test_client().get("/listone")

        assert _u21_di(risposta, "Listone U21 Under") == "si"
        assert _u21_di(risposta, "Listone U21 Over") == "no"

    def test_soglia_inclusiva(self, app, cur, db_isolato):
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        _crea_giocatore(cur, "Listone U21 Soglia", 2003)
        db_isolato.commit()

        risposta = app.test_client().get("/listone")

        assert _u21_di(risposta, "Listone U21 Soglia") == "si"

    def test_giocatore_senza_data_nascita_non_e_ne_u21_ne_non_u21(self, app, cur, db_isolato):
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        _crea_giocatore(cur, "Listone U21 SenzaData", None)
        db_isolato.commit()

        risposta = app.test_client().get("/listone")

        assert _u21_di(risposta, "Listone U21 SenzaData") == ""

    def test_filtro_mostrato_solo_con_soglia_configurata(self, app, cur, db_isolato):
        cur.execute("UPDATE general_config SET u21_threshold_year = 2003 WHERE id = 1;")
        db_isolato.commit()
        corpo = app.test_client().get("/listone").get_data(as_text=True)
        assert corpo.count('type="checkbox" data-u21=') == 2

        cur.execute("UPDATE general_config SET u21_threshold_year = NULL WHERE id = 1;")
        db_isolato.commit()
        assert 'type="checkbox" data-u21=' not in app.test_client().get("/listone").get_data(as_text=True)
