"""Draft live, livello dati: numeri delle pick, pick in corso, stato della sessione.

Ogni test gira in una transazione annullata a fine test (db_isolato), quindi
svuotare `draft` e `draft_sessione` qui non lascia traccia.
"""

from datetime import date

import pytest

pytestmark = pytest.mark.db

ANNO = 2031


@pytest.fixture
def due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    return righe[0]["nome"], righe[1]["nome"]


@pytest.fixture
def draft_a_due(cur, db_isolato, due_squadre):
    """Un draft di test: due squadre, tre giri, nessun numero ancora."""
    cur.execute("DELETE FROM draft;")
    cur.execute("DELETE FROM draft_sessione;")
    prima, seconda = due_squadre
    id_pick = 910000
    for giro in (1, 2, 3):
        for squadra in (prima, seconda):
            id_pick += 1
            cur.execute(
                """INSERT INTO draft (id, anno, giro, numero, detentore_att, detentore_originale)
                   VALUES (%s, %s, %s, NULL, %s, %s);""",
                (id_pick, date(ANNO, 1, 1), giro, squadra, squadra))
    db_isolato.commit()
    return prima, seconda


def _ordine(prima, seconda):
    # seconda ha chiuso ultima: sceglie per prima
    from app.domini.draft_ordine import ordine_da_classifica
    return ordine_da_classifica([(prima, 1), (seconda, 2)])


class TestNumeri:
    def test_assegna_i_numeri_per_giro_e_detentore_originale(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))

        pick = repo.pick_dell_anno(cur, ANNO)
        assert [(p["numero"], p["detentore_originale"]) for p in pick] == [
            (1, seconda), (2, prima), (3, seconda), (4, prima), (5, seconda), (6, prima)]

    def test_la_pick_scambiata_conserva_il_detentore_attuale(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        cur.execute("UPDATE draft SET detentore_att = %s WHERE giro = 1 AND detentore_originale = %s;",
                    (prima, seconda))
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))

        prima_pick = repo.pick_dell_anno(cur, ANNO)[0]
        assert prima_pick["numero"] == 1
        assert prima_pick["detentore_originale"] == seconda
        assert prima_pick["detentore_att"] == prima

    def test_rigenerare_l_ordine_non_viola_l_indice_unico(self, cur, draft_a_due):
        from app.domini.draft_ordine import ordine_da_classifica
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))
        # classifica ribaltata: i numeri si scambiano fra le stesse righe
        repo.assegna_numeri(cur, ANNO, ordine_da_classifica([(prima, 2), (seconda, 1)]))

        assert repo.pick_dell_anno(cur, ANNO)[0]["detentore_originale"] == prima

    def test_non_si_rigenera_a_draft_iniziato(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))
        cur.execute("UPDATE draft SET saltata = true WHERE numero = 1;")

        with pytest.raises(ValueError, match="iniziato"):
            repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))

    def test_pick_mancante_fa_fallire(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        cur.execute("DELETE FROM draft WHERE giro = 2 AND detentore_originale = %s;", (prima,))

        with pytest.raises(ValueError, match="ne serve esattamente una"):
            repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))


class TestPickInCorso:
    def test_senza_ordine_non_c_e_una_pick_in_corso(self, cur, draft_a_due):
        from app.repositories import draft as repo
        assert repo.pick_in_corso(cur, ANNO) is None

    def test_e_il_numero_piu_basso_libero(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))
        assert repo.pick_in_corso(cur, ANNO)["numero"] == 1

    def test_salta_le_pick_gia_saltate(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))
        cur.execute("UPDATE draft SET saltata = true WHERE numero IN (1, 2);")
        assert repo.pick_in_corso(cur, ANNO)["numero"] == 3

    def test_salta_le_pick_con_giocatore(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))
        cur.execute("SELECT id FROM giocatore LIMIT 1;")
        g = cur.fetchone()["id"]
        cur.execute("UPDATE draft SET id_giocatore_scelto = %s WHERE numero = 1;", (g,))
        assert repo.pick_in_corso(cur, ANNO)["numero"] == 2

    def test_draft_finito(self, cur, draft_a_due):
        from app.repositories import draft as repo
        prima, seconda = draft_a_due
        repo.assegna_numeri(cur, ANNO, _ordine(prima, seconda))
        cur.execute("UPDATE draft SET saltata = true;")
        assert repo.pick_in_corso(cur, ANNO) is None


class TestSessione:
    def test_il_percorso_preparato_aperto_chiuso(self, cur, draft_a_due):
        from app.repositories import draft_sessione as sess
        assert sess.leggi(cur, ANNO) is None
        assert sess.prepara(cur, ANNO)
        assert sess.leggi(cur, ANNO)["stato"] == "preparato"
        assert sess.apri(cur, ANNO)
        assert sess.aperto(cur)["anno"] == ANNO
        assert sess.chiudi(cur, ANNO)
        assert sess.leggi(cur, ANNO)["stato"] == "chiuso"
        assert sess.aperto(cur) is None

    def test_le_transizioni_non_si_ripetono(self, cur, draft_a_due):
        from app.repositories import draft_sessione as sess
        sess.prepara(cur, ANNO)
        assert sess.apri(cur, ANNO)
        assert not sess.apri(cur, ANNO)      # gia aperto
        assert not sess.prepara(cur, ANNO)   # a draft aperto l'ordine non si rigenera
        assert sess.chiudi(cur, ANNO)
        assert not sess.chiudi(cur, ANNO)

    def test_non_si_apre_senza_preparare(self, cur, draft_a_due):
        from app.repositories import draft_sessione as sess
        assert not sess.apri(cur, ANNO)

    def test_un_solo_draft_aperto_alla_volta(self, cur, draft_a_due):
        import psycopg2
        from app.repositories import draft_sessione as sess
        sess.prepara(cur, ANNO)
        sess.prepara(cur, ANNO + 1)
        sess.apri(cur, ANNO)
        cur.execute("SAVEPOINT s;")
        with pytest.raises(psycopg2.errors.UniqueViolation):
            sess.apri(cur, ANNO + 1)
        cur.execute("ROLLBACK TO SAVEPOINT s;")
