"""Riconoscimento delle squadre citate in un testo libero."""

from app.domini.movimenti import squadre_citate


class TestSquadreCitate:
    def test_trova_il_nome_esatto(self):
        assert squadre_citate("La squadra Sborada acquista Rossi", ["Sborada", "FC Pontos"]) == ["Sborada"]

    def test_nessun_nome_citato(self):
        assert squadre_citate("Nessuna squadra qui dentro", ["Sborada", "FC Pontos"]) == []

    def test_trova_entrambe_le_squadre_di_uno_scambio(self):
        """L'ordine del risultato segue l'elenco delle squadre note, non la
        posizione in cui compaiono nel testo."""
        testo = "Le squadre Diaolo Porco e Sborada hanno concluso uno scambio"
        assert squadre_citate(testo, ["Sborada", "Diaolo Porco", "FC Pontos"]) == ["Sborada", "Diaolo Porco"]

    def test_non_e_sensibile_al_maiuscolo(self):
        assert squadre_citate("la squadra SBORADA acquista", ["Sborada"]) == ["Sborada"]

    def test_nome_scritto_male_non_viene_trovato(self):
        """E' lo stesso limite che aveva l'ILIKE che sostituisce: un nome
        digitato in modo diverso da quello vero non puo' essere riconosciuto."""
        assert squadre_citate("Dialo Porco acquista Cataldi", ["Diaolo Porco"]) == []
