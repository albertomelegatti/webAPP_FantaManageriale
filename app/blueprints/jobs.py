"""
Route HTTP per far girare senza un vero scheduler i job che sincronizzano dati
da siti esterni (Transfermarkt, fantacalcio.it): pensate per essere "pingate"
periodicamente da un servizio esterno di uptime-monitoring (es. UptimeRobot)
al posto di un cron.

GET /jobs/aggiorna_transfermarkt?token=...
GET /jobs/aggiorna_campioncini?token=...

Stesso schema per entrambe, un token diverso per ciascuna (env
TRANSFERMARKT_JOB_TOKEN / FANTACALCIO_JOB_TOKEN):
- Autenticate con un token condiviso: a differenza delle altre route di questa
  app, eseguono scritture pesanti su richiesta e non possono restare aperte a
  chiunque scopra l'URL.
- Non girano più di una volta ogni tot ore (controllo sulla cache locale di
  ciascuna, transfermarkt_giocatori/fantacalcio_giocatori.aggiornato_il),
  anche se il servizio di ping le chiama più spesso.
- Non girano due volte in parallelo (pg_advisory_lock, una chiave diversa a
  testa): un ping duplicato/ripetuto durante un run in corso viene ignorato,
  non accodato.
- Rispondono subito e fanno il lavoro vero in un thread in background, per non
  far scadere il timeout del servizio di ping esterno - anche quando, come
  per i campioncini, il lavoro vero e' un solo secondo: un futuro
  rallentamento del sito sorgente non deve far apparire il job "giù".
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from psycopg2.extras import RealDictCursor

from app.core.db import get_connection, prova_lock, release_connection, rilascia_lock
from app.core.transfermarkt_api import recupera_valori_mercato
from app.domini.matching_transfermarkt import candidati_esatti, parse_data_tm
from app.repositories import fantacalcio as fantacalcio_repo
from app.repositories import transfermarkt as transfermarkt_repo
from app.services import fantacalcio as servizio_fantacalcio

from app.core.logging import get_logger

logger = get_logger(__name__)

jobs_bp = Blueprint('jobs', __name__, url_prefix='/jobs')

LOCK_KEY_TRANSFERMARKT = 918273645
LOCK_KEY_FANTACALCIO = 473829165
ORE_MINIME_TRA_RUN = 20
SOGLIA_MINIMA_GIOCATORI = 400
MASSIMO_CLUB_MANCANTI = 2
RE_ID_GIOCATORE = re.compile(r"/spieler/(\d+)")


class DumpNonAffidabile(Exception):
    """Il dump scaricato sembra incompleto/corrotto: nessuna scrittura viene eseguita."""


@jobs_bp.route("/aggiorna_transfermarkt", methods=["GET"])
def aggiorna_transfermarkt():
    token_atteso = os.getenv("TRANSFERMARKT_JOB_TOKEN")
    if not token_atteso or request.args.get("token") != token_atteso:
        return jsonify({"status": "non autorizzato"}), 403

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        ultimo = transfermarkt_repo.ultimo_aggiornamento(cur)
        if ultimo and ultimo > datetime.now(timezone.utc) - timedelta(hours=ORE_MINIME_TRA_RUN):
            release_connection(conn, cur)
            return jsonify({"status": "skipped", "motivo": "già eseguito di recente"}), 200

        if not prova_lock(cur, LOCK_KEY_TRANSFERMARKT):
            release_connection(conn, cur)
            return jsonify({"status": "skipped", "motivo": "già in esecuzione"}), 200

    except Exception:
        logger.exception("❌ Errore preliminare job transfermarkt")
        release_connection(conn, cur)
        return jsonify({"status": "errore"}), 500

    # Da qui in poi la connessione (con il lock) passa al thread in background,
    # che la rilascia lui stesso a fine lavoro (successo o eccezione).
    thread = threading.Thread(target=_esegui_job_in_background, args=(conn, cur), daemon=True)
    thread.start()
    return jsonify({"status": "avviato"}), 200


def _esegui_job_in_background(conn, cur):
    try:
        with tempfile.TemporaryDirectory() as workdir:
            percorso_players = _scarica_rosa_serie_a(workdir)
            _esegui_matching(cur, percorso_players)
        conn.commit()
        logger.info("✅ Job transfermarkt completato con successo.")
    except Exception:
        conn.rollback()
        logger.exception("❌ Job transfermarkt fallito")
    finally:
        try:
            rilascia_lock(cur, LOCK_KEY_TRANSFERMARKT)
            conn.commit()
        except Exception:
            logger.exception("⚠️ Errore nel rilascio del lock")
        release_connection(conn, cur)


@jobs_bp.route("/aggiorna_campioncini", methods=["GET"])
def aggiorna_campioncini():
    token_atteso = os.getenv("FANTACALCIO_JOB_TOKEN")
    if not token_atteso or request.args.get("token") != token_atteso:
        return jsonify({"status": "non autorizzato"}), 403

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        ultimo = fantacalcio_repo.ultimo_aggiornamento(cur)
        if ultimo and ultimo > datetime.now(timezone.utc) - timedelta(hours=ORE_MINIME_TRA_RUN):
            release_connection(conn, cur)
            return jsonify({"status": "skipped", "motivo": "già eseguito di recente"}), 200

        if not prova_lock(cur, LOCK_KEY_FANTACALCIO):
            release_connection(conn, cur)
            return jsonify({"status": "skipped", "motivo": "già in esecuzione"}), 200

    except Exception:
        logger.exception("❌ Errore preliminare job campioncini")
        release_connection(conn, cur)
        return jsonify({"status": "errore"}), 500

    thread = threading.Thread(target=_esegui_job_campioncini_in_background, args=(conn, cur), daemon=True)
    thread.start()
    return jsonify({"status": "avviato"}), 200


def _esegui_job_campioncini_in_background(conn, cur):
    try:
        riepilogo = servizio_fantacalcio.sincronizza(cur)
        conn.commit()
        logger.info(f"✅ Job campioncini completato: {riepilogo}")
    except Exception:
        conn.rollback()
        logger.exception("❌ Job campioncini fallito")
    finally:
        try:
            rilascia_lock(cur, LOCK_KEY_FANTACALCIO)
            conn.commit()
        except Exception:
            logger.exception("⚠️ Errore nel rilascio del lock")
        release_connection(conn, cur)


def _stagione_corrente():
    oggi = datetime.now(timezone.utc)
    return oggi.year if oggi.month >= 7 else oggi.year - 1


def _esegui_tfmkt(comando, input_path, output_path, workdir, extra_args=None):
    # CRAWLEE_STORAGE_DIR: senza impostarla, crawlee scrive la sua cache locale
    # (coda richieste/dataset) relativa alla working directory del processo Flask,
    # sporcandola in produzione. La reindirizziamo nella tempdir del job, ripulita
    # automaticamente alla fine.
    env = {**os.environ, "CRAWLEE_STORAGE_DIR": os.path.join(workdir, ".crawlee")}
    argv = [sys.executable, "-m", "tfmkt", comando] + (extra_args or [])
    with open(output_path, "w", encoding="utf-8") as out:
        stdin = open(input_path, encoding="utf-8") if input_path else None
        try:
            subprocess.run(argv, stdin=stdin, stdout=out, env=env, check=True, timeout=300)
        finally:
            if stdin:
                stdin.close()


def _scarica_rosa_serie_a(workdir):
    stagione = str(_stagione_corrente())

    confederations = os.path.join(workdir, "confederations.json")
    competitions = os.path.join(workdir, "competitions.json")
    serie_a = os.path.join(workdir, "serie_a.json")
    clubs = os.path.join(workdir, "clubs.json")
    players = os.path.join(workdir, "players.json")

    _esegui_tfmkt("confederations", None, confederations, workdir)
    _esegui_tfmkt("competitions", confederations, competitions, workdir, ["-p", confederations])

    with open(competitions, encoding="utf-8") as f, open(serie_a, "w", encoding="utf-8") as out:
        for riga in f:
            dato = json.loads(riga)
            if dato.get("competition_type") == "first_tier" and dato.get("country_code") == "IT1":
                out.write(riga)

    _esegui_tfmkt("clubs", serie_a, clubs, workdir, ["-p", serie_a, "-s", stagione])

    n_club = sum(1 for _ in open(clubs, encoding="utf-8"))
    if n_club != 20:
        raise DumpNonAffidabile(f"Attesi 20 club, trovati {n_club}: probabile scraping fallito/bloccato.")

    _esegui_tfmkt("players", clubs, players, workdir, ["-p", clubs, "-s", stagione])
    return players


def _carica_giocatori_transfermarkt(percorso_input):
    per_club_tm = {}
    with open(percorso_input, encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            dato = json.loads(riga)
            match_id = RE_ID_GIOCATORE.search(dato.get("href") or "")
            if not match_id:
                continue
            club_tm = (dato.get("parent") or {}).get("name")
            cognome = dato.get("last_name") or dato.get("name") or ""
            per_club_tm.setdefault(club_tm, []).append({
                "id_transfermarkt": int(match_id.group(1)),
                "cognome": cognome,
                "nome": dato.get("name") or "",
                "nome_completo": f"{dato.get('name') or ''} {cognome}".strip(),
                "club_tm": club_tm,
                "data_nascita": parse_data_tm(dato.get("date_of_birth")),
                "scadenza_contratto": parse_data_tm(dato.get("contract_expires")),
                # Il valore di mercato lo mette _arricchisci_valori_mercato
                # dall'API ceapi: non è nel dump.
            })
    return per_club_tm


def _arricchisci_valori_mercato(giocatori_tm_per_club_tm):
    """Mette su ogni giocatore del dump il valore di mercato preso dall'API
    ceapi. Un id non risolto resta None: il refresh più sotto non sovrascrive
    mai con None un valore già a DB."""
    tutti = [g for giocatori in giocatori_tm_per_club_tm.values() for g in giocatori]
    valori = recupera_valori_mercato(g["id_transfermarkt"] for g in tutti)
    for g in tutti:
        g["valore_mercato"] = valori.get(g["id_transfermarkt"])


def _esegui_matching(cur, percorso_input):
    giocatori_tm_per_club_tm = _carica_giocatori_transfermarkt(percorso_input)

    totale_giocatori = sum(len(v) for v in giocatori_tm_per_club_tm.values())
    if totale_giocatori < SOGLIA_MINIMA_GIOCATORI:
        raise DumpNonAffidabile(
            f"Solo {totale_giocatori} giocatori nel dump (attesi almeno {SOGLIA_MINIMA_GIOCATORI})."
        )

    _arricchisci_valori_mercato(giocatori_tm_per_club_tm)

    per_id_transfermarkt = {
        g["id_transfermarkt"]: g
        for giocatori in giocatori_tm_per_club_tm.values()
        for g in giocatori
    }

    mappa_club = transfermarkt_repo.mappa_club(cur)

    club_mancanti = [nome for nome in mappa_club.values() if nome not in giocatori_tm_per_club_tm]
    if len(club_mancanti) > MASSIMO_CLUB_MANCANTI:
        raise DumpNonAffidabile(f"{len(club_mancanti)} club mancanti dal dump.")

    transfermarkt_repo.svuota_cache(cur)
    for giocatori in giocatori_tm_per_club_tm.values():
        for g in giocatori:
            transfermarkt_repo.inserisci_in_cache(cur, g)

    # Refresh dei già mappati: id_transfermarkt non viene mai ricalcolato.
    n_aggiornati = 0
    for g in transfermarkt_repo.gia_mappati(cur):
        aggiornato = per_id_transfermarkt.get(g["id_transfermarkt"])
        if not aggiornato:
            continue
        # Valore di mercato: si aggiorna solo se l'API ne ha dato uno nuovo; un
        # recupero fallito (None) tiene quello già a DB invece di azzerarlo.
        valore_mercato = (aggiornato["valore_mercato"]
                          if aggiornato["valore_mercato"] is not None
                          else g["valore_mercato"])
        if (aggiornato["data_nascita"] == g["data_nascita"]
                and aggiornato["scadenza_contratto"] == g["scadenza_contratto"]
                and valore_mercato == g["valore_mercato"]):
            continue
        transfermarkt_repo.aggiorna_dati_sincronizzati(
            cur, g["id"], aggiornato["data_nascita"], aggiornato["scadenza_contratto"], valore_mercato)
        n_aggiornati += 1

    n_auto = n_ambigui = n_non_trovati = 0
    for giocatore in transfermarkt_repo.non_ancora_mappati(cur):
        club_tm = mappa_club.get(giocatore["club"])
        candidati = candidati_esatti(giocatore["nome"], giocatori_tm_per_club_tm.get(club_tm, []))

        if len(candidati) == 1:
            transfermarkt_repo.assegna_abbinamento(cur, giocatore["id"], candidati[0])
            n_auto += 1
        elif len(candidati) >= 2:
            transfermarkt_repo.segnala_candidati_ambigui(
                cur, giocatore["id"], [c["id_transfermarkt"] for c in candidati])
            n_ambigui += 1
        else:
            transfermarkt_repo.segnala_non_trovato(cur, giocatore["id"])
            n_non_trovati += 1

    logger.error(f"🔄 Aggiornati: {n_aggiornati} | ✅ Nuovi: {n_auto} | ⚠️ Ambigui: {n_ambigui} | ❌ Non trovati: {n_non_trovati}")
