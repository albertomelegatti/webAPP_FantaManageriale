"""Admin: compilazione dell'albo d'oro e modifica degli stadi.

Come gli altri test di scrittura girano dentro una transazione annullata alla
fine (db_isolato): le route committano davvero, il database non conserva nulla.
La parte di validazione e' pura e non tocca il database.
"""

from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

from app.core.errori import ErroreDominio
from app.domini import albo_oro as dominio

SQUADRE = ["Alfa", "Beta", "Gamma", "Delta"]


def _form(**campi):
    """Griglia minima: Campionato a 4 posizioni, Final 4 a 2, Girone A a 2."""
    base = MultiDict([("stagione", "90-91"), ("camp_n", "4"),
                      ("fase_idx", "0"), ("fase_0_nome", "Final 4"), ("fase_0_n", "2"),
                      ("fase_idx", "1"), ("fase_1_nome", "Girone A"), ("fase_1_n", "2")])
    for chiave, valore in campi.items():
        base[chiave] = valore
    return base


class TestValidazione:
    def test_stagione_deve_essere_di_due_anni_consecutivi(self):
        assert dominio.stagione_valida("25-26") == "25-26"
        assert dominio.stagione_valida("99-00") == "99-00"
        for sbagliata in ("", "2025-26", "25-27", "26-25", "25/26", None):
            with pytest.raises(ErroreDominio):
                dominio.stagione_valida(sbagliata)

    def test_stadio(self):
        assert dominio.stadio_valido(" Arena ", "3") == ("Arena", 3)
        for nome, livello in (("", "1"), ("Arena", "9"), ("Arena", "-1"), ("Arena", "")):
            with pytest.raises(ErroreDominio):
                dominio.stadio_valido(nome, livello)


class TestPiazzamentiDaForm:
    def test_le_posizioni_vuote_non_producono_righe(self):
        form = _form(camp_squadra_1="Alfa", camp_crediti_1="50", camp_squadra_3="Beta",
                     fase_0_squadra_1="Alfa")
        righe = dominio.piazzamenti_da_form(form, SQUADRE)
        assert [(r["competizione"], r["fase"], r["posizione"], r["squadra"]) for r in righe] == [
            ("Campionato", None, 1, "Alfa"),
            ("Campionato", None, 3, "Beta"),
            ("Coppa", "Final 4", 1, "Alfa"),
        ]
        assert righe[0]["crediti_generati"] == 50
        assert righe[1]["crediti_generati"] == 0, "crediti vuoti = 0"

    def test_squadra_sconosciuta(self):
        with pytest.raises(ErroreDominio):
            dominio.piazzamenti_da_form(_form(camp_squadra_1="Svincolato"), SQUADRE)

    def test_stessa_squadra_due_volte_nella_stessa_fase(self):
        with pytest.raises(ErroreDominio):
            dominio.piazzamenti_da_form(_form(camp_squadra_1="Alfa", camp_squadra_2="Alfa"), SQUADRE)

    def test_stessa_squadra_in_fasi_diverse_va_bene(self):
        form = _form(camp_squadra_1="Alfa", fase_0_squadra_1="Alfa", fase_1_squadra_1="Alfa")
        assert len(dominio.piazzamenti_da_form(form, SQUADRE)) == 3

    def test_crediti_non_validi(self):
        for crediti in ("-1", "abc"):
            with pytest.raises(ErroreDominio):
                dominio.piazzamenti_da_form(_form(camp_squadra_1="Alfa", camp_crediti_1=crediti), SQUADRE)

    def test_fase_compilata_senza_nome(self):
        with pytest.raises(ErroreDominio):
            dominio.piazzamenti_da_form(_form(fase_0_nome=" ", fase_0_squadra_1="Alfa"), SQUADRE)

    def test_fase_senza_nome_e_senza_squadre_si_ignora(self):
        assert dominio.piazzamenti_da_form(_form(fase_0_nome=""), SQUADRE) == []


class TestVistaStagione:
    def test_stagione_vuota_ha_comunque_le_fasi_standard(self):
        vista = dominio.vista_stagione([], 10)
        assert len(vista["campionato"]) == 10
        assert [f["nome"] for f in vista["coppa"]] == ["Final 4", "Girone A", "Girone B"]
        assert [len(f["slot"]) for f in vista["coppa"]] == [2, 5, 5]

    def test_riporta_le_righe_esistenti_e_le_fasi_extra(self):
        righe = [
            {"competizione": "Campionato", "fase": None, "squadra": "Alfa", "posizione": 1, "crediti_generati": 90},
            {"competizione": "Coppa", "fase": "Playoff", "squadra": "Beta", "posizione": 6, "crediti_generati": 5},
        ]
        vista = dominio.vista_stagione(righe, 4)
        assert vista["campionato"][0] == {"posizione": 1, "squadra": "Alfa", "crediti": 90}
        playoff = next(f for f in vista["coppa"] if f["nome"] == "Playoff")
        assert len(playoff["slot"]) == 6 and playoff["slot"][5]["squadra"] == "Beta"
        assert vista["coppa"][0]["nome"] == "Final 4", "le finali stanno prima"


def _client(app, admin=True):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logged_in=True, is_admin=admin, username="admin" if admin else "test")
    return c


@pytest.mark.db
class TestAccesso:
    def test_anonimo_e_squadra_non_entrano(self, app, client, client_squadra):
        for c in (client, client_squadra):
            for url in ("/admin/", "/admin/albo_oro", "/admin/stadi", "/admin/crediti"):
                risposta = c.get(url)
                assert risposta.status_code == 302, url

    def test_squadra_non_scrive_sull_albo(self, app, cur, db_isolato, client_squadra, nome_squadra):
        client_squadra.post("/admin/albo_oro", data={
            "stagione": "90-91", "camp_n": "1", "camp_squadra_1": nome_squadra})
        cur.execute("SELECT 1 FROM albo_oro WHERE stagione = '90-91';")
        assert cur.fetchone() is None

    def test_admin_apre_le_pagine(self, client_admin):
        for url in ("/admin/albo_oro", "/admin/stadi", "/admin/albo_oro?stagione=90-91"):
            assert client_admin.get(url).status_code == 200, url


def _righe(cur, stagione="90-91"):
    cur.execute("""SELECT competizione::text AS competizione, fase, posizione, squadra, crediti_generati
                   FROM albo_oro WHERE stagione = %s ORDER BY competizione, fase NULLS FIRST, posizione;""",
                (stagione,))
    return [dict(r) for r in cur.fetchall()]


def _due_squadre(cur):
    cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 2;")
    return [r["nome"] for r in cur.fetchall()]


@pytest.mark.db
class TestAlboOro:
    def _post(self, app, **campi):
        dati = {"stagione": "90-91", "camp_n": "3", "fase_idx": ["0"], "fase_0_nome": "Final 4", "fase_0_n": "2"}
        dati.update(campi)
        return _client(app).post("/admin/albo_oro", data=dati)

    def test_compila_modifica_e_svuota_una_posizione(self, app, cur, db_isolato):
        a, b = _due_squadre(cur)
        self._post(app, camp_squadra_1=a, camp_crediti_1="50", camp_squadra_2=b,
                   fase_0_squadra_1=b, fase_0_crediti_1="10")
        assert _righe(cur) == [
            {"competizione": "Campionato", "fase": None, "posizione": 1, "squadra": a, "crediti_generati": 50},
            {"competizione": "Campionato", "fase": None, "posizione": 2, "squadra": b, "crediti_generati": 0},
            {"competizione": "Coppa", "fase": "Final 4", "posizione": 1, "squadra": b, "crediti_generati": 10},
        ]

        # scambio di posizione fra le due squadre + una posizione svuotata
        self._post(app, camp_squadra_1=b, camp_crediti_1="50", camp_squadra_2=a, fase_0_squadra_1="")
        righe = _righe(cur)
        assert [(r["posizione"], r["squadra"]) for r in righe if r["competizione"] == "Campionato"] == [(1, b), (2, a)]
        assert not [r for r in righe if r["competizione"] == "Coppa"]

    def test_non_tocca_le_altre_stagioni_ne_i_crediti_delle_squadre(self, app, cur, db_isolato):
        a, _ = _due_squadre(cur)
        cur.execute("SELECT count(*) AS n FROM albo_oro WHERE stagione <> '90-91';")
        altre = cur.fetchone()["n"]
        cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (a,))
        crediti = cur.fetchone()["crediti"]

        self._post(app, camp_squadra_1=a, camp_crediti_1="500")

        cur.execute("SELECT count(*) AS n FROM albo_oro WHERE stagione <> '90-91';")
        assert cur.fetchone()["n"] == altre
        cur.execute("SELECT crediti FROM squadra WHERE nome = %s;", (a,))
        assert cur.fetchone()["crediti"] == crediti

    def test_dati_non_validi_non_toccano_nulla(self, app, cur, db_isolato):
        a, _ = _due_squadre(cur)
        self._post(app, camp_squadra_1=a)
        prima = _righe(cur)
        for cattivo in ({"camp_squadra_2": a},               # squadra doppia
                        {"camp_squadra_2": "Non esiste"},    # squadra sconosciuta
                        {"camp_crediti_1": "-3"}):           # crediti negativi
            risposta = self._post(app, camp_squadra_1=a, **cattivo)
            assert risposta.status_code == 302
            assert _righe(cur) == prima

    def test_non_svuota_una_stagione_per_errore(self, app, cur, db_isolato):
        a, _ = _due_squadre(cur)
        self._post(app, camp_squadra_1=a)
        self._post(app)  # nessuna posizione compilata
        assert len(_righe(cur)) == 1

    def test_stagione_non_valida(self, app, cur, db_isolato):
        a, _ = _due_squadre(cur)
        self._post(app, stagione="2025", camp_squadra_1=a)
        cur.execute("SELECT 1 FROM albo_oro WHERE stagione = '2025';")
        assert cur.fetchone() is None

    def test_la_pagina_mostra_le_righe_registrate(self, app, cur, db_isolato):
        a, _ = _due_squadre(cur)
        self._post(app, camp_squadra_1=a, camp_crediti_1="77")
        html = _client(app).get("/admin/albo_oro?stagione=90-91").get_data(as_text=True)
        assert 'name="camp_crediti_1" min="0" step="1" value="77"' in html
        assert f'<option value="{a}" data-username=' in html
        assert 'selected' in html


@pytest.mark.db
class TestStadi:
    def test_modifica_nome_e_livello(self, app, cur, db_isolato):
        cur.execute("SELECT proprietario, nome FROM stadio LIMIT 1;")
        stadio = cur.fetchone()
        if not stadio:
            pytest.skip("Nessuno stadio.")
        sq = stadio["proprietario"]
        _client(app).post("/admin/stadi", data={
            "squadra": [sq], f"nome_{sq}": "Stadio di prova", f"livello_{sq}": "5"})
        cur.execute("SELECT nome, livello FROM stadio WHERE proprietario = %s;", (sq,))
        assert dict(cur.fetchone()) == {"nome": "Stadio di prova", "livello": 5}

    def test_livello_fuori_scala_non_salva(self, app, cur, db_isolato):
        cur.execute("SELECT proprietario, nome, livello FROM stadio LIMIT 1;")
        stadio = cur.fetchone()
        if not stadio:
            pytest.skip("Nessuno stadio.")
        sq = stadio["proprietario"]
        _client(app).post("/admin/stadi", data={
            "squadra": [sq], f"nome_{sq}": "Altro", f"livello_{sq}": "99"})
        cur.execute("SELECT nome, livello FROM stadio WHERE proprietario = %s;", (sq,))
        assert dict(cur.fetchone()) == {"nome": stadio["nome"], "livello": stadio["livello"]}


SCHEMA_RENDITE = Path(__file__).resolve().parent.parent / "CronJob" / "stadio_livello_schema.sql"


@pytest.fixture
def tabella_rendite(cur, db_isolato):
    """Crea (e popola) stadio_livello se manca, dentro la transazione del test.

    Lo script e' quello vero di CronJob/, che l'utente lancia a mano: qui gira
    sulla connessione isolata, quindi il DDL viene annullato a fine test e non
    tocca lo schema del database di sviluppo.
    """
    cur.execute(SCHEMA_RENDITE.read_text(encoding="utf-8"))
    db_isolato.commit()  # savepoint: un rollback della route non deve portarsi via la tabella


@pytest.mark.db
class TestRendite:
    def test_senza_tabella_si_usa_il_default_e_la_modifica_e_bloccata(self, app, cur, db_isolato):
        cur.execute("SELECT to_regclass('stadio_livello') IS NOT NULL AS esiste;")
        if cur.fetchone()["esiste"]:
            pytest.skip("La tabella esiste gia' sul database di sviluppo.")
        pagina = _client(app).get("/admin/stadi").get_data(as_text=True)
        assert "stadio_livello_schema.sql" in pagina
        risposta = _client(app).post("/admin/stadi/rendite", data={"rendita_0": "0"})
        assert risposta.status_code == 302

    def test_lo_script_e_idempotente_e_parte_dalla_scala_del_regolamento(self, cur, tabella_rendite):
        cur.execute(SCHEMA_RENDITE.read_text(encoding="utf-8"))  # secondo lancio: nessun errore
        cur.execute("SELECT livello, rendita FROM stadio_livello ORDER BY livello;")
        righe = [dict(r) for r in cur.fetchall()]
        assert [r["livello"] for r in righe] == list(range(9))
        assert all(r["rendita"] >= 0 for r in righe)

    def test_modifica_le_rendite_e_la_pagina_pubblica_le_usa(self, app, cur, tabella_rendite):
        dati = {f"rendita_{i}": str(i * 100) for i in range(9)}
        _client(app).post("/admin/stadi/rendite", data=dati)
        cur.execute("SELECT rendita FROM stadio_livello ORDER BY livello;")
        assert [r["rendita"] for r in cur.fetchall()] == [i * 100 for i in range(9)]

        cur.execute("SELECT livello FROM stadio WHERE livello = 2 LIMIT 1;")
        if cur.fetchone():
            pubblica = app.test_client().get("/crediti_stadi_slot").get_data(as_text=True)
            assert "+200/anno" in pubblica

    def test_valori_non_validi_non_salvano_niente(self, app, cur, tabella_rendite):
        cur.execute("SELECT rendita FROM stadio_livello ORDER BY livello;")
        prima = [r["rendita"] for r in cur.fetchall()]
        for cattivo in ("-1", "abc", "", "1001"):
            dati = {f"rendita_{i}": "5" for i in range(9)}
            dati["rendita_4"] = cattivo
            _client(app).post("/admin/stadi/rendite", data=dati)
            cur.execute("SELECT rendita FROM stadio_livello ORDER BY livello;")
            assert [r["rendita"] for r in cur.fetchall()] == prima, cattivo

    def test_squadra_non_modifica_le_rendite(self, client_squadra, cur, tabella_rendite):
        cur.execute("SELECT rendita FROM stadio_livello ORDER BY livello;")
        prima = [r["rendita"] for r in cur.fetchall()]
        client_squadra.post("/admin/stadi/rendite", data={f"rendita_{i}": "999" for i in range(9)})
        cur.execute("SELECT rendita FROM stadio_livello ORDER BY livello;")
        assert [r["rendita"] for r in cur.fetchall()] == prima

    def test_il_livello_massimo_degli_stadi_segue_le_rendite(self, app, cur, tabella_rendite):
        cur.execute("SELECT proprietario, nome, livello FROM stadio LIMIT 1;")
        stadio = cur.fetchone()
        if not stadio:
            pytest.skip("Nessuno stadio.")
        sq = stadio["proprietario"]
        _client(app).post("/admin/stadi", data={"squadra": [sq], f"nome_{sq}": stadio["nome"], f"livello_{sq}": "8"})
        cur.execute("SELECT livello FROM stadio WHERE proprietario = %s;", (sq,))
        assert cur.fetchone()["livello"] == 8


def test_lo_script_parte_dagli_stessi_valori_del_default_nel_codice():
    """Se si cambia la scala in uno dei due posti e non nell'altro, l'app
    mostrerebbe valori diversi prima e dopo aver lanciato lo script."""
    import re
    from app.services.crediti_stadi_slot import RENDITA_STADIO

    sql = SCHEMA_RENDITE.read_text(encoding="utf-8")
    coppie = re.findall(r"\((\d+),\s*(\d+)\)", sql.split("VALUES", 1)[1])
    assert [int(r) for _, r in coppie] == list(RENDITA_STADIO)
    assert [int(l) for l, _ in coppie] == list(range(len(RENDITA_STADIO)))


class TestRenditeDaAccreditare:
    def test_solo_chi_ha_uno_stadio_che_rende(self):
        from app.services.crediti_stadi_slot import RENDITA_STADIO, rendite_da_accreditare

        squadre = [{"nome": "A", "stadio_livello": 2}, {"nome": "B", "stadio_livello": 0},
                   {"nome": "C", "stadio_livello": None}, {"nome": "D", "stadio_livello": 8}]
        assert rendite_da_accreditare(squadre, list(RENDITA_STADIO)) == [("A", 8), ("D", 44)]


def _crediti_tutti(cur):
    cur.execute("SELECT nome, crediti FROM squadra;")
    return {r["nome"]: r["crediti"] for r in cur.fetchall()}


@pytest.mark.db
class TestAccreditoRendite:
    @pytest.fixture(autouse=True)
    def _registro_libero(self, cur, db_isolato):
        """L'accredito si fa una volta per stagione: se su dev e' gia' stato fatto davvero,
        la riga del registro bloccherebbe questi test. La si toglie, nella transazione di prova."""
        from app.core.tempo import oggi
        from app.domini.accrediti import chiave_rendite_stadi, stagione_corrente

        cur.execute("DELETE FROM accrediti_annuali WHERE chiave = %s;",
                    (chiave_rendite_stadi(stagione_corrente(oggi())),))
        db_isolato.commit()

    def _attesi(self, cur):
        from app.repositories import squadre as squadre_repo
        from app.services.crediti_stadi_slot import rendite_da_accreditare, rendite_in_uso

        return dict(rendite_da_accreditare(squadre_repo.tutte_con_stadio(cur), rendite_in_uso(cur)))

    def _client_con_gettone(self, app):
        c = _client(app)
        c.get("/admin/stadi")  # la pagina emette il gettone monouso
        with c.session_transaction() as s:
            return c, s["token_rendite"]

    def test_accredita_la_rendita_a_ogni_squadra(self, app, cur, db_isolato):
        prima, attesi = _crediti_tutti(cur), self._attesi(cur)
        assert attesi, "servono squadre con uno stadio che rende"
        c, token = self._client_con_gettone(app)

        c.post("/admin/stadi/accredita_rendite", data={"token": token})

        dopo = _crediti_tutti(cur)
        for nome, crediti in prima.items():
            assert dopo[nome] == crediti + attesi.get(nome, 0), nome

    def test_un_secondo_invio_con_lo_stesso_gettone_non_accredita_di_nuovo(self, app, cur, db_isolato):
        c, token = self._client_con_gettone(app)
        c.post("/admin/stadi/accredita_rendite", data={"token": token})
        dopo_il_primo = _crediti_tutti(cur)

        c.post("/admin/stadi/accredita_rendite", data={"token": token})

        assert _crediti_tutti(cur) == dopo_il_primo

    def test_senza_gettone_o_con_gettone_sbagliato_non_accredita(self, app, cur, db_isolato):
        prima = _crediti_tutti(cur)
        c, token = self._client_con_gettone(app)
        c.post("/admin/stadi/accredita_rendite", data={})
        c, token = self._client_con_gettone(app)
        c.post("/admin/stadi/accredita_rendite", data={"token": "sbagliato"})
        assert _crediti_tutti(cur) == prima

    def test_una_squadra_non_puo_accreditare(self, app, cur, db_isolato, client_squadra):
        prima = _crediti_tutti(cur)
        client_squadra.post("/admin/stadi/accredita_rendite", data={"token": "x"})
        assert _crediti_tutti(cur) == prima

    def test_il_pulsante_e_nella_pagina(self, app):
        pagina = _client(app).get("/admin/stadi").get_data(as_text=True)
        assert "Accredita rendite a tutte le squadre" in pagina
        assert 'name="token"' in pagina
