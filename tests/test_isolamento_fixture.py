"""
La fixture di isolamento non deve poter essere scavalcata.

Nasce da un incidente: una simulazione temporanea scritta con
`cur.connection.commit()` ha raggiunto la connessione grezza, scavalcato i
savepoint e committato sul serio, lasciando prestiti e crediti alterati sul
database di sviluppo.
"""

import pytest

pytestmark = pytest.mark.db


def test_il_cursore_riporta_al_proxy_non_alla_connessione_grezza(cur, db_isolato):
    """La via di fuga che ha causato l'incidente."""
    assert cur.connection is db_isolato, \
        "cur.connection deve essere il proxy, altrimenti .commit() scavalca i savepoint"


def test_un_commit_via_cursore_resta_dentro_la_transazione(cur, db_isolato, nome_squadra):
    """Anche committando dal cursore, la modifica non deve sopravvivere al test."""
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    prima = cur.fetchone()["crediti"]
    cur.execute("UPDATE squadra SET crediti = crediti + 777 WHERE nome = %s;", (nome_squadra,))
    cur.connection.commit()
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    assert cur.fetchone()["crediti"] == prima + 777


def test_la_modifica_precedente_non_e_sopravvissuta(cur, nome_squadra):
    """Gira dopo il test sopra: se il commit fosse arrivato al database vero,
    qui i crediti sarebbero 777 in piu'."""
    cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (nome_squadra,))
    assert cur.fetchone()["crediti"] < 700
