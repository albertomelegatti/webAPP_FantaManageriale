"""Draft live, servizio: apertura, scelta, pick saltate, chiusura.

Tutto in una transazione annullata a fine test (db_isolato). Due squadre, tre
giri, sei pick; `seconda` ha chiuso ultima e sceglie per prima:
numeri 1,3,5 = seconda; 2,4,6 = prima.
"""

from datetime import date

import pytest

pytestmark = pytest.mark.db

ANNO = 2031
SOGLIA = 2006


def _giocatore(cur, nome, anno_nascita=2008, ruolo="PlaceHolderRole"):
    cur.execute(
        """INSERT INTO giocatore (
               nome, ruolo, tipo_contratto, squadra_att, detentore_cartellino,
               quot_att_mantra, costo, priorita, club, data_nascita)
           VALUES (%s, ARRAY[%s]::ruolo_mantra[], 'Svincolato',
                   'Svincolato', 'Svincolato', 1, 0, 1, 'Test', %s)
           RETURNING id;""",
        (nome, ruolo, f"{anno_nascita}-06-15" if anno_nascita else None))
    return cur.fetchone()["id"]


@pytest.fixture
def draft(cur, db_isolato):
    """Draft preparato (non aperto): (prima, seconda, ordine_pick)."""
    from app.domini.draft_ordine import ordine_da_classifica
    from app.repositories import draft as draft_repo
    from app.repositories import draft_sessione as sessione

    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    righe = cur.fetchall()
    if len(righe) < 2:
        pytest.skip("Servono due squadre.")
    prima, seconda = righe[0]["nome"], righe[1]["nome"]

    cur.execute("UPDATE general_config SET u21_threshold_year = %s WHERE id = 1;", (SOGLIA,))
    # Parto da zero Primavera per le due squadre: i test sugli slot li riempiono da soli.
    cur.execute(
        """UPDATE giocatore SET tipo_contratto = 'Indeterminato'
           WHERE squadra_att IN (%s, %s) AND tipo_contratto = 'Primavera';""", (prima, seconda))
    cur.execute("DELETE FROM draft;")
    cur.execute("DELETE FROM draft_sessione;")
    id_pick = 920000
    for giro in (1, 2, 3):
        for squadra in (prima, seconda):
            id_pick += 1
            cur.execute(
                """INSERT INTO draft (id, anno, giro, numero, detentore_att, detentore_originale)
                   VALUES (%s, %s, %s, NULL, %s, %s);""",
                (id_pick, date(ANNO, 1, 1), giro, squadra, squadra))
    draft_repo.assegna_numeri(cur, ANNO, ordine_da_classifica([(prima, 1), (seconda, 2)]))
    sessione.prepara(cur, ANNO)
    db_isolato.commit()
    return prima, seconda


@pytest.fixture
def aperto(cur, draft):
    from app.services import draft_live
    draft_live.apri(cur, ANNO)
    return draft


def _in_corso(cur):
    from app.repositories import draft as draft_repo
    return draft_repo.pick_in_corso(cur, ANNO)


def _scegli(cur, id_giocatore, *, squadra, e_admin=False, id_pick=None):
    from app.services import draft_live
    pick = _in_corso(cur)
    return draft_live.scegli(cur, ANNO, id_pick or pick["id"], id_giocatore,
                             squadra=squadra, e_admin=e_admin, da=squadra)


def _riempi_primavera(cur, squadra, quanti):
    for i in range(quanti):
        g = _giocatore(cur, f"Slot {squadra} {i}")
        cur.execute(
            """UPDATE giocatore SET tipo_contratto = 'Primavera', squadra_att = %s,
                                    detentore_cartellino = %s WHERE id = %s;""",
            (squadra, squadra, g))


class TestScelta:
    def test_il_giocatore_va_in_primavera_a_costo_zero(self, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (seconda,))
        crediti = cur.fetchone()["crediti"]

        esito = _scegli(cur, g, squadra=seconda)

        cur.execute("SELECT tipo_contratto, squadra_att, detentore_cartellino FROM giocatore WHERE id = %s;", (g,))
        riga = cur.fetchone()
        assert (riga["tipo_contratto"], riga["squadra_att"], riga["detentore_cartellino"]) == (
            "Primavera", seconda, seconda)
        cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (seconda,))
        assert cur.fetchone()["crediti"] == crediti
        assert esito["pick"]["numero"] == 1

    def test_la_pick_risulta_usata_e_il_turno_avanza(self, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        _scegli(cur, g, squadra=seconda)

        cur.execute("SELECT id_giocatore_scelto, scelta_da, scelta_il FROM draft WHERE numero = 1;")
        riga = cur.fetchone()
        assert riga["id_giocatore_scelto"] == g
        assert riga["scelta_da"] == seconda
        assert riga["scelta_il"] is not None
        assert _in_corso(cur)["numero"] == 2

    def test_un_portiere_e_draftabile(self, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Portierino", ruolo="Por")
        _scegli(cur, g, squadra=seconda)
        cur.execute("SELECT tipo_contratto FROM giocatore WHERE id = %s;", (g,))
        assert cur.fetchone()["tipo_contratto"] == "Primavera"


class TestPermessi:
    def test_non_e_il_turno_della_squadra(self, cur, aperto):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        with pytest.raises(SceltaNonValida, match="turno"):
            _scegli(cur, g, squadra=prima)

    def test_l_admin_sceglie_per_la_squadra_assente(self, cur, aperto):
        prima, seconda = aperto
        g = _giocatore(cur, "Giovane Uno")
        _scegli(cur, g, squadra="admin", e_admin=True)
        cur.execute("SELECT squadra_att FROM giocatore WHERE id = %s;", (g,))
        assert cur.fetchone()["squadra_att"] == seconda   # alla squadra on the clock, non all'admin

    def test_pick_vecchia_viene_rifiutata(self, cur, aperto):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = aperto
        vecchia = _in_corso(cur)["id"]
        _scegli(cur, _giocatore(cur, "Giovane Uno"), squadra=seconda)
        with pytest.raises(SceltaNonValida, match="turno e' cambiato"):
            _scegli(cur, _giocatore(cur, "Giovane Due"), squadra=seconda, id_pick=vecchia)

    def test_draft_non_aperto(self, cur, draft):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = draft
        with pytest.raises(SceltaNonValida, match="non e' aperto"):
            _scegli(cur, _giocatore(cur, "Giovane Uno"), squadra=seconda)


class TestGiocatoreDraftabile:
    def test_un_over_21_non_si_puo_scegliere(self, cur, aperto):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = aperto
        vecchio = _giocatore(cur, "Veterano", anno_nascita=SOGLIA - 1)
        with pytest.raises(SceltaNonValida, match="non e' draftabile"):
            _scegli(cur, vecchio, squadra=seconda)

    def test_senza_data_di_nascita_non_si_puo_dire(self, cur, aperto):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = aperto
        senza = _giocatore(cur, "Senza Data", anno_nascita=None)
        with pytest.raises(SceltaNonValida):
            _scegli(cur, senza, squadra=seconda)

    def test_un_giocatore_con_squadra_non_si_puo_scegliere(self, cur, aperto):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = aperto
        g = _giocatore(cur, "Gia Preso")
        cur.execute("UPDATE giocatore SET tipo_contratto = 'Indeterminato', squadra_att = %s, "
                    "detentore_cartellino = %s WHERE id = %s;", (prima, prima, g))
        with pytest.raises(SceltaNonValida):
            _scegli(cur, g, squadra=seconda)

    def test_promosso_e_poi_tagliato_non_e_piu_draftabile(self, cur, aperto):
        from app.repositories import giocatori as giocatori_repo
        prima, seconda = aperto
        g = _giocatore(cur, "Promosso Tagliato")
        cur.execute("INSERT INTO giocatore_storico (giocatore, squadra, dal, al, fonte) "
                    "VALUES (%s, %s, now(), now(), 'promozione');", (g, prima))
        assert giocatori_repo.draftabili(cur, SOGLIA, g) == []

    def test_il_pool_elenca_gli_u21_svincolati(self, cur, aperto):
        from app.repositories import giocatori as giocatori_repo
        giovane = _giocatore(cur, "Giovane Pool")
        vecchio = _giocatore(cur, "Vecchio Pool", anno_nascita=SOGLIA - 1)
        ids = {g["id"] for g in giocatori_repo.draftabili(cur, SOGLIA)}
        assert giovane in ids and vecchio not in ids

    def test_senza_soglia_il_pool_e_vuoto(self, cur, aperto):
        from app.repositories import giocatori as giocatori_repo
        _giocatore(cur, "Giovane Pool")
        assert giocatori_repo.draftabili(cur, None) == []


class TestSlotPrimavera:
    def test_a_slot_pieni_la_pick_salta_da_sola_all_apertura(self, cur, draft):
        from app.services import draft_live
        prima, seconda = draft
        _riempi_primavera(cur, seconda, 5)

        esito = draft_live.apri(cur, ANNO)

        assert [p["numero"] for p in esito["saltate"]] == [1]
        assert _in_corso(cur)["numero"] == 2
        cur.execute("SELECT saltata, scelta_da FROM draft WHERE numero = 1;")
        riga = cur.fetchone()
        assert riga["saltata"] and riga["scelta_da"] == "sistema"

    def test_lo_slot_che_si_riempie_durante_il_draft_fa_saltare_le_pick_successive(self, cur, aperto):
        prima, seconda = aperto
        _riempi_primavera(cur, prima, 4)
        _scegli(cur, _giocatore(cur, "Giovane Uno"), squadra=seconda)      # pick 1
        _scegli(cur, _giocatore(cur, "Giovane Due"), squadra=prima)        # pick 2 -> prima a 5 slot
        # pick 3 (seconda) tocca a seconda; poi pick 4 (prima) deve saltare
        esito = _scegli(cur, _giocatore(cur, "Giovane Tre"), squadra=seconda)
        assert [p["numero"] for p in esito["saltate"]] == [4]
        assert _in_corso(cur)["numero"] == 5

    def test_la_scelta_a_slot_pieni_e_rifiutata(self, cur, aperto):
        from app.services.draft_live import SceltaNonValida
        prima, seconda = aperto
        _riempi_primavera(cur, seconda, 5)
        with pytest.raises(SceltaNonValida, match="slot Primavera"):
            _scegli(cur, _giocatore(cur, "Giovane Uno"), squadra=seconda)


class TestSaltoEChiusura:
    def test_l_admin_salta_la_pick_dell_assente(self, cur, aperto):
        from app.services import draft_live
        prima, seconda = aperto
        pick = _in_corso(cur)
        esito = draft_live.salta(cur, ANNO, pick["id"], da="admin")
        assert esito["pick"]["numero"] == 1
        assert _in_corso(cur)["numero"] == 2

    def test_il_draft_si_chiude_quando_finiscono_le_pick(self, cur, aperto):
        from app.repositories import draft_sessione as sessione
        from app.services import draft_live
        prima, seconda = aperto
        for i in range(5):
            _scegli(cur, _giocatore(cur, f"Giovane {i}"), squadra=_in_corso(cur)["detentore_att"])
        assert sessione.leggi(cur, ANNO)["stato"] == "aperto"

        pick = _in_corso(cur)
        esito = draft_live.salta(cur, ANNO, pick["id"], da="admin")

        assert esito["concluso"] is True
        assert sessione.leggi(cur, ANNO)["stato"] == "chiuso"
        assert _in_corso(cur) is None

    def test_non_si_apre_senza_ordine(self, cur, draft):
        from app.services import draft_live
        cur.execute("UPDATE draft SET numero = NULL;")
        with pytest.raises(draft_live.SceltaNonValida, match="ordine"):
            draft_live.apri(cur, ANNO)
