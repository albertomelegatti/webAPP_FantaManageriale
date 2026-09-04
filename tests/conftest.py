"""
Fixture condivise della suite.

Due garanzie di sicurezza, perché i test girano contro un database Supabase vero
(quello di sviluppo puntato da DATABASE_URL in locale, distinto dalla produzione
su Render):

1. `_blocca_ambiente_di_produzione` interrompe l'intera sessione se l'ambiente
   sembra la produzione, o se il progetto Supabase collegato non è quello
   dichiarato in TEST_DB_PROJECT_REF (quando la variabile è impostata).
2. `_silenzia_telegram` neutralizza l'invio di messaggi *prima* che qualunque
   test possa farne partire uno.

I test di questa fase sono inoltre di sola lettura per costruzione: esercitano
solo route GET, quindi anche un puntamento sbagliato non può alterare dati.
"""

import os
from urllib.parse import urlparse

import pytest
from dotenv import load_dotenv

load_dotenv()


def _ref_progetto(database_url):
    """'postgres.abcdefgh' -> 'abcdefgh': il project ref Supabase è nello username."""
    utente = urlparse(database_url).username or ""
    _, _, ref = utente.partition(".")
    return ref or utente


def pytest_configure(config):
    """Guardia d'ambiente: gira prima della raccolta dei test, non dopo."""
    if os.getenv("RENDER") or os.getenv("FLASK_ENV") == "production":
        pytest.exit("Suite bloccata: sembra un ambiente di produzione.", returncode=2)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.exit("DATABASE_URL non impostata: impossibile eseguire la suite.", returncode=2)

    ref_atteso = os.getenv("TEST_DB_PROJECT_REF")
    ref_effettivo = _ref_progetto(database_url)
    if ref_atteso and ref_atteso != ref_effettivo:
        pytest.exit(
            f"Suite bloccata: DATABASE_URL punta al progetto '{ref_effettivo}', "
            f"ma TEST_DB_PROJECT_REF dichiara '{ref_atteso}'.",
            returncode=2,
        )

    config.stash["host_db"] = urlparse(database_url).hostname


@pytest.fixture(scope="session", autouse=True)
def _silenzia_telegram():
    """
    Nessun messaggio Telegram parte durante i test.

    Serve sia il flag sia lo stub della coda: NOTIFICATIONS_ENABLED viene
    calcolato all'import di telegram_utils (che fa load_dotenv con override=True,
    quindi impostare la variabile d'ambiente da qui non basterebbe), e alcune
    funzioni accodano senza passare da send_message().
    """
    import telegram_utils

    telegram_utils.NOTIFICATIONS_ENABLED = False
    telegram_utils._enqueue_telegram_message = lambda chat_id, text_to_send: None
    yield


@pytest.fixture(scope="session")
def app(_silenzia_telegram):
    """
    L'app Flask reale.

    L'import di `main` ha effetti collaterali (init_pool e caricamento della
    mappa ID Telegram), quindi avviene qui dentro e una volta sola per sessione.
    """
    import main

    main.app.config.update(
        TESTING=True,
        # Il test client parla http://, con il cookie marcato Secure la sessione
        # non verrebbe mai rimandata indietro.
        SESSION_COOKIE_SECURE=False,
        WTF_CSRF_ENABLED=False,
    )
    return main.app


@pytest.fixture
def client(app):
    """Client anonimo, nessuna sessione impostata."""
    return app.test_client()


@pytest.fixture
def client_squadra(app, nome_squadra):
    """Client autenticato come squadra, senza passare dal form di login."""
    c = app.test_client()
    with c.session_transaction() as sessione:
        sessione["logged_in"] = True
        sessione["is_admin"] = False
        sessione["nome_squadra"] = nome_squadra
        sessione["username"] = "test"
    return c


@pytest.fixture
def gate_aperto(app, monkeypatch):
    """
    Neutralizza i gate di chiusura di mercato, aste e prestiti.

    Senza questo, se nel DB di sviluppo le date di chiusura sono passate, i
    `before_request` dei blueprint reindirizzano e il corpo delle route non viene
    mai eseguito: gli smoke test resterebbero verdi coprendo solo il redirect,
    proprio sui moduli più complessi del progetto.

    La patch è sul riferimento *dentro ogni blueprint*, non su queries: i moduli
    importano le funzioni per valore (`from queries import mercato_aperto`), quindi
    sostituire l'originale non avrebbe effetto. Nessuna scrittura sul database.
    """
    import user_aste
    import user_mercato
    import user_prestiti

    monkeypatch.setattr(user_aste, "aste_aperte", lambda conn: True)
    monkeypatch.setattr(user_mercato, "mercato_aperto", lambda conn: True)
    monkeypatch.setattr(user_prestiti, "mercato_aperto", lambda conn: True)
    yield


@pytest.fixture
def client_admin(app):
    """Client autenticato come admin."""
    c = app.test_client()
    with c.session_transaction() as sessione:
        sessione["logged_in"] = True
        sessione["is_admin"] = True
        sessione["username"] = "admin"
    return c


# --- Dati reali presi dal DB di sviluppo, per riempire i parametri delle route ---

@pytest.fixture(scope="session")
def _dati_reali(app):
    """
    Un identificativo valido per ogni tipo di parametro presente nelle route.
    Una sola connessione per sessione: le fixture derivate leggono da qui.
    """
    from db import get_connection, release_connection
    from psycopg2.extras import RealDictCursor

    conn = cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT nome FROM squadra WHERE nome <> 'Svincolato' ORDER BY nome LIMIT 1;")
        riga = cur.fetchone()
        squadra = riga["nome"] if riga else None

        cur.execute("SELECT id FROM giocatore WHERE squadra_att = %s LIMIT 1;", (squadra,))
        riga = cur.fetchone()
        giocatore = riga["id"] if riga else None

        cur.execute("SELECT id FROM asta ORDER BY id DESC LIMIT 1;")
        riga = cur.fetchone()
        asta = riga["id"] if riga else None

        cur.execute("SELECT id FROM scambio ORDER BY id DESC LIMIT 1;")
        riga = cur.fetchone()
        scambio = riga["id"] if riga else None

        return {"squadra": squadra, "giocatore": giocatore, "asta": asta, "scambio": scambio}
    finally:
        release_connection(conn, cur)


@pytest.fixture(scope="session")
def nome_squadra(_dati_reali):
    if not _dati_reali["squadra"]:
        pytest.skip("Nessuna squadra nel database di sviluppo.")
    return _dati_reali["squadra"]
