"""
Smoke test di tutte le route GET: nessuna deve rispondere 5xx.

È il test più economico della suite e quello che intercetta la maggior parte
delle rotture da refactoring (import spezzati, variabili rinominate, template
che perdono un parametro). Non verifica il *contenuto* delle pagine: verifica
che l'applicazione stia in piedi.

I casi sono generati dalla url_map invece che da un elenco scritto a mano, così
quando le route si sposteranno in app/blueprints/ la copertura resta automatica.
Solo GET: nessun test di questo file scrive sul database.
"""

import pytest

# Route escluse dalla generazione automatica, con la ragione.
ROUTE_ESCLUSE = {
    # Avvia lo scraping Transfermarkt (~2 minuti) e scrive sul DB.
    # Il caso senza token è comunque coperto da test_job_transfermarkt_richiede_token.
    "jobs.aggiorna_transfermarkt",
    # Servita da Flask, non è codice di questo progetto.
    "static",
}

# Come riempire i parametri dinamici delle route.
PARAMETRI = {
    "nome_squadra": "squadra",
    "id_giocatore": "giocatore",
    "asta_id": "asta",
    "scambio_id": "scambio",
}


def _url_get(app, dati):
    """(endpoint, url) per ogni route GET con i parametri riempiti da dati reali."""
    casi = []
    for regola in app.url_map.iter_rules():
        if regola.endpoint in ROUTE_ESCLUSE or "GET" not in regola.methods:
            continue

        valori = {}
        parametri_mancanti = False
        for argomento in regola.arguments:
            chiave = PARAMETRI.get(argomento)
            if chiave is None or dati.get(chiave) is None:
                parametri_mancanti = True
                break
            valori[argomento] = dati[chiave]

        if parametri_mancanti:
            continue

        with app.test_request_context():
            from flask import url_for

            casi.append((regola.endpoint, url_for(regola.endpoint, **valori)))

    return sorted(casi)


@pytest.fixture(scope="session")
def casi_get(app, _dati_reali):
    casi = _url_get(app, _dati_reali)
    assert casi, "Nessuna route GET raccolta: la generazione dei casi è rotta."
    return casi


def test_tutte_le_route_get_raccolte(casi_get):
    """Sentinella: se il numero crolla, la generazione dei casi si è rotta in silenzio."""
    assert len(casi_get) >= 20


@pytest.mark.db
def test_nessuna_route_get_risponde_5xx(client_squadra, casi_get, gate_aperto):
    """
    Un solo test per tutte le route, così il report elenca *tutti* i fallimenti
    invece di fermarsi al primo.

    `gate_aperto` serve a eseguire davvero il corpo delle route di mercato/aste/
    prestiti anche quando nel DB di sviluppo le date di chiusura sono passate.
    """
    fallite = []
    for endpoint, url in casi_get:
        risposta = client_squadra.get(url)
        if risposta.status_code >= 500:
            fallite.append(f"{endpoint} ({url}) -> {risposta.status_code}")

    assert not fallite, "Route che rispondono 5xx:\n  " + "\n  ".join(fallite)


@pytest.mark.db
def test_gate_chiuso_reindirizza_invece_di_errore(client_squadra, nome_squadra):
    """
    Con i gate al loro stato reale, le sezioni chiuse devono reindirizzare
    (302) e mai restituire un errore. Se nel DB sono aperte, rispondono 200:
    entrambi gli esiti sono corretti, un 5xx no.
    """
    for url in (f"/mercato/mercato/{nome_squadra}",
                f"/aste/aste/{nome_squadra}",
                f"/prestiti/prestiti/{nome_squadra}"):
        assert client_squadra.get(url).status_code in (200, 302), url


@pytest.mark.db
def test_route_pubbliche_rispondono_200(client):
    """Le pagine senza autenticazione devono essere raggiungibili da chiunque."""
    for url in ("/", "/login", "/squadre", "/listone", "/aste", "/vetrina/vetrina",
                "/movimenti_mercato", "/crediti_stadi_slot", "/health"):
        risposta = client.get(url)
        assert risposta.status_code == 200, f"{url} -> {risposta.status_code}"


@pytest.mark.db
def test_health_check_riporta_ok(client):
    risposta = client.get("/health")
    assert risposta.status_code == 200
    assert risposta.get_json() == {"status": "ok"}


def test_job_transfermarkt_richiede_token(client):
    """Senza token la route non deve avviare nulla."""
    assert client.get("/jobs/aggiorna_transfermarkt").status_code == 403
    assert client.get("/jobs/aggiorna_transfermarkt?token=sbagliato").status_code == 403


@pytest.mark.db
def test_login_reindirizza_se_gia_autenticato(client_squadra, nome_squadra):
    risposta = client_squadra.get("/login")
    assert risposta.status_code == 302
    assert "squadra_login" in risposta.headers["Location"]


@pytest.mark.db
def test_logout_pulisce_la_sessione(client_squadra):
    risposta = client_squadra.get("/logout")
    assert risposta.status_code == 302
    with client_squadra.session_transaction() as sessione:
        assert "nome_squadra" not in sessione
        assert "logged_in" not in sessione


@pytest.mark.db
def test_admin_puo_aprire_le_pagine_admin(client_admin):
    for url in ("/admin/", "/admin/crediti", "/admin/chiusura_mercato_aste",
                "/admin/invia_comunicazione", "/admin/richiesta/modifica/contratto",
                "/admin/verifica_corrispondenze_giocatori"):
        risposta = client_admin.get(url)
        assert risposta.status_code < 500, f"{url} -> {risposta.status_code}"
