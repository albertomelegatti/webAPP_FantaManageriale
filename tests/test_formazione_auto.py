"""Test per app/domini/formazione_auto.py: funzioni pure, nessun database."""

from app.domini.formazione_auto import schiera


def _g(id_, ruolo, quot=10):
    return {"id": id_, "ruolo": ruolo, "quot_att_mantra": quot}


class TestSchieraTitolari:
    def test_ogni_giocatore_nel_suo_slot(self):
        modulo = [("Por",), ("Dc",), ("A",)]
        rosa = [_g(1, "Por"), _g(2, "Dc"), _g(3, "A")]

        righe = schiera(modulo, rosa)

        assert righe == [
            {"tit": 1, "ris": None, "ter": None},
            {"tit": 2, "ris": None, "ter": None},
            {"tit": 3, "ris": None, "ter": None},
        ]

    def test_a_parita_di_slot_vince_il_piu_quotato(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "Dc", quot=15), _g(2, "Dc", quot=30)]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 2
        assert righe[0]["ris"] == 1

    def test_slot_piu_specifico_preferito_a_parita_di_combacio(self):
        # "C" e' il ruolo piu' offensivo sia dello slot singolo sia di M/C:
        # un giocatore col solo ruolo C combacia con entrambi, ma deve
        # riempire prima quello specifico per lasciare M/C a chi ha bisogno
        # anche del ruolo M.
        modulo = [("M", "C"), ("C",)]
        rosa = [_g(1, "C")]

        righe = schiera(modulo, rosa)

        assert righe[1]["tit"] == 1
        assert righe[0]["tit"] is None

    def test_ruolo_piu_difensivo_del_giocatore_e_quello_che_conta(self):
        # Dd/E vale come Dd (il piu' difensivo): non deve finire in uno slot
        # che accetta solo E.
        modulo = [("Dd",), ("E",)]
        rosa = [_g(1, "Dd,E")]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 1
        assert righe[1]["tit"] is None


class TestSchieraPanchina:
    def test_terzo_giocatore_compatibile_va_in_riserva_poi_seconda_riserva(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "Dc", quot=30), _g(2, "Dc", quot=20), _g(3, "Dc", quot=10)]

        righe = schiera(modulo, rosa)

        assert righe[0] == {"tit": 1, "ris": 2, "ter": 3}

    def test_panchina_piena_lascia_il_giocatore_fuori(self):
        modulo = [("Dc",)]
        rosa = [_g(i, "Dc", quot=40 - i) for i in range(4)]  # 4 giocatori, un solo slot

        righe = schiera(modulo, rosa)

        assert righe[0] == {"tit": 0, "ris": 1, "ter": 2}
        # il 4o (id=3, il meno quotato) non compare da nessuna parte
        assegnati = {righe[0]["tit"], righe[0]["ris"], righe[0]["ter"]}
        assert 3 not in assegnati

    def test_riserva_va_sotto_lo_slot_con_meno_riserve(self):
        modulo = [("Dc",), ("Dc",)]
        rosa = [
            _g(1, "Dc", quot=40), _g(2, "Dc", quot=30),  # riempiono i due titolari
            _g(3, "Dc", quot=20),  # riserva del primo slot libero trovato
            _g(4, "Dc", quot=10),  # deve andare sotto l'altro slot, non fare 2 riserve sullo stesso
        ]

        righe = schiera(modulo, rosa)

        riserve_per_slot = [{r["ris"], r["ter"]} - {None} for r in righe]
        assert len(riserve_per_slot[0]) == 1
        assert len(riserve_per_slot[1]) == 1


class TestSchieraCasiLimite:
    def test_giocatore_senza_slot_compatibile_resta_fuori(self):
        modulo = [("Por",)]
        rosa = [_g(1, "A")]

        righe = schiera(modulo, rosa)

        assert righe == [{"tit": None, "ris": None, "ter": None}]

    def test_rosa_vuota(self):
        modulo = [("Por",), ("Dc",)]

        righe = schiera(modulo, [])

        assert righe == [
            {"tit": None, "ris": None, "ter": None},
            {"tit": None, "ris": None, "ter": None},
        ]

    def test_quotazione_mancante_non_esplode_e_conta_come_zero(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "Dc", quot=None), _g(2, "Dc", quot=5)]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 2
        assert righe[0]["ris"] == 1

    def test_ruolo_vuoto_non_esplode(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "")]

        righe = schiera(modulo, rosa)

        assert righe == [{"tit": None, "ris": None, "ter": None}]
