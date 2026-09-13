"""
Conteggi per tutte le squadre in una interrogazione invece di due.

La pagina di nuovo scambio mostra, per ogni squadra, slot liberi, slot prestiti
e crediti spendibili. Erano quattro aggregazioni piu' una lettura a parte per la
squadra loggata: due scansioni di `giocatore` e due di `asta`, raggruppate sulla
stessa colonna con soli filtri diversi.
"""

import pytest

pytestmark = pytest.mark.db


def _squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome;")
    return [r["nome"] for r in cur.fetchall()]


class TestSlotPerSquadra:
    def test_coincide_con_i_conteggi_singoli(self, cur):
        """L'aggregazione condizionale deve dare esattamente cio' che davano le
        due query separate, per ogni squadra."""
        from app.repositories import giocatori as repo
        mappa = repo.slot_per_squadra(cur)
        for squadra in _squadre(cur):
            atteso = (repo.slot_occupati_da_giocatori(cur, squadra),
                      repo.slot_prestiti_in(cur, squadra))
            ottenuto = (mappa.get(squadra, {}).get("giocatori", 0),
                        mappa.get(squadra, {}).get("prestiti", 0))
            assert atteso == ottenuto, f"{squadra}: {atteso} vs {ottenuto}"

    def test_una_squadra_senza_giocatori_non_compare(self, cur):
        """Chi non ha righe in `giocatore` non compare nel raggruppamento: il
        chiamante deve usare un valore di default, non assumere la chiave."""
        from app.repositories import giocatori as repo
        assert "Squadra Inesistente" not in repo.slot_per_squadra(cur)


class TestImpegniPerSquadra:
    def test_coincide_con_i_conteggi_singoli(self, cur):
        from app.repositories import aste as repo
        mappa = repo.impegni_per_squadra(cur)
        for squadra in _squadre(cur):
            atteso = (repo.slot_impegnati(cur, squadra), repo.offerta_totale(cur, squadra))
            ottenuto = (mappa.get(squadra, {}).get("slot", 0),
                        mappa.get(squadra, {}).get("offerta", 0))
            assert atteso == ottenuto, f"{squadra}: {atteso} vs {ottenuto}"

    def test_l_offerta_conta_solo_le_aste_in_cui_si_e_in_testa(
        self, cur, db_isolato, nome_squadra
    ):
        """Partecipare a un'asta impegna uno slot; i crediti li impegna solo chi
        ha l'offerta piu' alta."""
        from app.repositories import aste as repo
        cur.execute("SELECT nome FROM squadra WHERE nome NOT IN (%s,'Svincolato') LIMIT 1;",
                    (nome_squadra,))
        altra = cur.fetchone()["nome"]
        cur.execute("SELECT id FROM giocatore WHERE tipo_contratto='Svincolato' LIMIT 1;")
        giocatore = cur.fetchone()["id"]
        cur.execute(
            """INSERT INTO asta (giocatore, squadra_vincente, ultima_offerta, tempo_fine_asta,
                                 stato, partecipanti, gia_elaborata)
               VALUES (%s, %s, 30, (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day',
                       'in_corso', %s, FALSE);""",
            (giocatore, altra, [nome_squadra, altra]))
        db_isolato.commit()

        mappa = repo.impegni_per_squadra(cur)
        assert mappa[nome_squadra]["slot"] >= 1, "partecipare impegna uno slot"
        assert mappa[altra]["offerta"] >= 30, "chi e' in testa impegna i crediti"
