"""
Application factory.

Sostituisce il codice a livello di modulo che stava in main.py: la
configurazione e la registrazione dei blueprint avvengono dentro create_app(),
così l'app può essere costruita più volte (test) invece che una sola volta come
effetto collaterale di un import.
"""

import os
import time

from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from flask_compress import Compress

_ASSET_V_TTL = 5  # secondi: evita uno stat() del file a ogni singola riga/richiesta
_asset_v_cache = {}


def _asset_v(static_folder, rel_path):
    """Timestamp di modifica di un file statico, da usare come ?v= per invalidare la cache del browser quando il file cambia.

    Il risultato viene tenuto in cache per qualche secondo: senza, una pagina con
    molte righe (es. la Rosa con 25-30 giocatori) farebbe uno stat() del
    filesystem per ogni riga a ogni caricamento.
    """
    now = time.monotonic()
    cached = _asset_v_cache.get(rel_path)
    if cached and now - cached[1] < _ASSET_V_TTL:
        return cached[0]

    try:
        value = int(os.path.getmtime(os.path.join(static_folder, rel_path)))
    except OSError:
        value = 0

    _asset_v_cache[rel_path] = (value, now)
    return value


def _registra_blueprint(app):
    # Import qui dentro e non in testa al modulo: i blueprint importano da
    # `app.*`, quindi importarli a livello di modulo creerebbe un ciclo.
    from app.blueprints.admin import admin_bp
    from app.blueprints.aste import aste_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.jobs import jobs_bp
    from app.blueprints.mercato import mercato_bp
    from app.blueprints.prestiti import prestiti_bp
    from app.blueprints.pubblico import pubblico_bp
    from app.blueprints.rosa import rosa_bp
    from app.blueprints.user import user_bp
    from app.blueprints.vetrina import vetrina_bp
    from app.blueprints.webhook import webhook_bp

    app.register_blueprint(pubblico_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(aste_bp)
    app.register_blueprint(mercato_bp)
    app.register_blueprint(prestiti_bp)
    app.register_blueprint(rosa_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(vetrina_bp)
    app.register_blueprint(jobs_bp)


def create_app():
    from app.core.db import init_pool
    from app.telegram_utils import get_all_telegram_ids

    load_dotenv()

    app = Flask(__name__)

    init_pool()

    app.secret_key = os.getenv("SECRET_KEY", "chiave_segreta_default_per_sviluppo")

    app.config['SESSION_PERMANENT'] = True
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600 * 24 * 30  # 30 giorni invece di 365
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # Cache lato browser per gli asset statici (CSS/JS/immagini) e compressione gzip/br delle risposte
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 60 * 60 * 24 * 1  # 1 giorno di cache su immagini statiche
    Compress(app)

    app.jinja_env.globals['asset_v'] = lambda rel_path: _asset_v(app.static_folder, rel_path)

    # Inizializza il dizionario telegram al lancio dell'app
    app.config['SQUADRE_TELEGRAM_IDS'] = get_all_telegram_ids()

    _registra_blueprint(app)

    @app.errorhandler(500)
    def handle_500(error):
        """Handler specifico per errori 500"""
        return redirect(url_for('pubblico.home')), 500

    return app
