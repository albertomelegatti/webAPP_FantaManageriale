"""Test per app/domini/formazione_auto.py: funzioni pure, nessun database."""

from app.domini.formazione_auto import schiera
from app.domini.moduli import normalizza_slot


def _g(id_, ruolo, quot=10):
    return {"id": id_, "ruolo": ruolo, "quot_att_mantra": quot}


class TestSchieraTitolari:
    def test_ogni_giocatore_nel_suo_slot(self):
        modulo = [("Por",), ("Dc",), ("A",)]
        rosa = [_g(1, "Por"), _g(2, "Dc"), _g(3, "A")]

        righe = schiera(modulo, rosa)

        assert righe == [
            {"tit": 1, "ris": []},
            {"tit": 2, "ris": []},
            {"tit": 3, "ris": []},
        ]

    def test_a_parita_di_slot_vince_il_piu_quotato(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "Dc", quot=15), _g(2, "Dc", quot=30)]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 2
        assert righe[0]["ris"] == [1]

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

    def test_slot_e_va_al_piu_offensivo_anche_se_meno_quotato(self):
        # Uno slot "E" puro puo' sembrare coperto sia da un Dd/E sia da un
        # E/W, ma il ruolo-chiave di Dd/E e' Dd (il suo piu' difensivo), non
        # E: non e' un candidato per questo slot, a prescindere da quanto
        # sia piu' quotato dell'E/W (il cui ruolo-chiave e' invece proprio E).
        modulo = [("E",)]
        rosa = [_g(1, "Dd,E", quot=30), _g(2, "E,W", quot=10)]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 2

    def test_slot_ds_va_al_ds_puro_non_al_dc_ds(self):
        # Dc e' piu' difensivo di Ds (un centrale prima di un terzino): il
        # ruolo-chiave di un Dc/Ds e' Dc, non Ds, quindi non e' candidato per
        # uno slot Ds puro nemmeno se piu' quotato del Ds puro.
        modulo = [("Ds",)]
        rosa = [_g(1, "Dc,Ds", quot=30), _g(2, "Ds", quot=10)]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 2

    def test_slot_m_va_al_m_puro_non_al_m_e(self):
        # M e' piu' difensivo di E (un mediano prima di un esterno): il
        # ruolo-chiave di un M/E e' M, quindi resta candidato per uno slot M
        # puro (a differenza dei casi sopra, qui il combacio c'e' davvero).
        modulo = [("M",)]
        rosa = [_g(1, "M,E", quot=10), _g(2, "C", quot=30)]  # il secondo non c'entra nulla col ruolo

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 1

    def test_t_e_w_sono_a_pari_rango(self):
        # T e W sono allo stesso rango difensivo: un giocatore W/A (chiave W)
        # e uno T/A (chiave T) sono entrambi candidati per uno slot T/W.
        modulo = [("T", "W")]
        rosa = [_g(1, "W,A", quot=10), _g(2, "T,A", quot=30)]

        righe = schiera(modulo, rosa)

        # il piu' quotato dei due prende il titolare, l'altro la riserva
        assert righe[0]["tit"] == 2
        assert righe[0]["ris"] == [1]


class TestSchieraPanchina:
    def test_panchina_in_ordine_di_quotazione(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "Dc", quot=30), _g(2, "Dc", quot=20), _g(3, "Dc", quot=10)]

        righe = schiera(modulo, rosa)

        assert righe[0] == {"tit": 1, "ris": [2, 3]}

    def test_panchina_piena_lascia_il_giocatore_fuori(self):
        modulo = [("Dc",)]
        rosa = [_g(i, "Dc", quot=40 - i) for i in range(6)]  # 6 giocatori, un solo slot

        righe = schiera(modulo, rosa)

        assert righe[0] == {"tit": 0, "ris": [1, 2, 3, 4]}
        # il 6o (id=5, il meno quotato) non compare da nessuna parte
        assert 5 not in {righe[0]["tit"], *righe[0]["ris"]}

    def test_riserva_va_sotto_lo_slot_con_meno_riserve(self):
        modulo = [("Dc",), ("Dc",)]
        rosa = [
            _g(1, "Dc", quot=40), _g(2, "Dc", quot=30),  # riempiono i due titolari
            _g(3, "Dc", quot=20),  # riserva del primo slot libero trovato
            _g(4, "Dc", quot=10),  # deve andare sotto l'altro slot, non fare 2 riserve sullo stesso
        ]

        righe = schiera(modulo, rosa)

        assert len(righe[0]["ris"]) == 1
        assert len(righe[1]["ris"]) == 1


class TestSchieraCasiLimite:
    def test_giocatore_senza_slot_compatibile_resta_fuori(self):
        modulo = [("Por",)]
        rosa = [_g(1, "A")]

        righe = schiera(modulo, rosa)

        assert righe == [{"tit": None, "ris": []}]

    def test_rosa_vuota(self):
        modulo = [("Por",), ("Dc",)]

        righe = schiera(modulo, [])

        assert righe == [
            {"tit": None, "ris": []},
            {"tit": None, "ris": []},
        ]

    def test_quotazione_mancante_non_esplode_e_conta_come_zero(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "Dc", quot=None), _g(2, "Dc", quot=5)]

        righe = schiera(modulo, rosa)

        assert righe[0]["tit"] == 2
        assert righe[0]["ris"] == [1]

    def test_ruolo_vuoto_non_esplode(self):
        modulo = [("Dc",)]
        rosa = [_g(1, "")]

        righe = schiera(modulo, rosa)

        assert righe == [{"tit": None, "ris": []}]


class TestNormalizzaSlot:
    def test_formato_vecchio_a_due_posti_diventa_lista(self):
        assert normalizza_slot({"tit": 1, "ris": 2, "ter": 3}) == {"tit": 1, "ris": [2, 3]}

    def test_formato_vecchio_con_buchi(self):
        assert normalizza_slot({"tit": 1, "ris": None, "ter": 3}) == {"tit": 1, "ris": [3]}

    def test_formato_nuovo_resta_uguale(self):
        assert normalizza_slot({"tit": 1, "ris": [2, 3, 4, 5]}) == {"tit": 1, "ris": [2, 3, 4, 5]}

    def test_slot_mancante(self):
        assert normalizza_slot(None) == {"tit": None, "ris": []}
