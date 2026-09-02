"""
Route HTTP per far girare il job di abbinamento Transfermarkt senza bisogno di un
vero scheduler: pensata per essere "pingata" periodicamente da un servizio esterno
di uptime-monitoring (es. UptimeRobot) al posto di un cron.

GET /jobs/aggiorna_transfermarkt?token=...

- Autenticata con un token condiviso (env TRANSFERMARKT_JOB_TOKEN): a differenza
  delle altre route di questa app, questa esegue scritture pesanti su richiesta e
  non può restare aperta a chiunque scopra l'URL.
- Non gira più di una volta ogni ~20 ore (controllo su transfermarkt_giocatori.aggiornato_il),
  anche se il servizio di ping la chiama più spesso.
- Non gira due volte in parallelo (pg_advisory_lock): un ping duplicato/ripetuto
  durante un run in corso viene ignorato, non accodato.
- Risponde subito e fa il lavoro vero (scraping ~2 minuti) in un thread in
  background, per non far scadere il timeout del servizio di ping esterno.
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

from db import get_connection, release_connection
from transfermarkt_matching import candidati_esatti, parse_data_tm

jobs_bp = Blueprint('jobs', __name__, url_prefix='/jobs')

LOCK_KEY_TRANSFERMARKT = 918273645
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

        cur.execute("SELECT max(aggiornato_il) AS ultimo FROM transfermarkt_giocatori;")
        ultimo = cur.fetchone()["ultimo"]
        if ultimo and ultimo > datetime.now(timezone.utc) - timedelta(hours=ORE_MINIME_TRA_RUN):
            release_connection(conn, cur)
            return jsonify({"status": "skipped", "motivo": "già eseguito di recente"}), 200

        cur.execute("SELECT pg_try_advisory_lock(%s) AS ottenuto;", (LOCK_KEY_TRANSFERMARKT,))
        if not cur.fetchone()["ottenuto"]:
            release_connection(conn, cur)
            return jsonify({"status": "skipped", "motivo": "già in esecuzione"}), 200

    except Exception as e:
        print(f"❌ Errore preliminare job transfermarkt: {e}")
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
        print("✅ Job transfermarkt completato con successo.")
    except Exception as e:
        conn.rollback()
        print(f"❌ Job transfermarkt fallito: {e}")
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s);", (LOCK_KEY_TRANSFERMARKT,))
            conn.commit()
        except Exception as e:
            print(f"⚠️ Errore nel rilascio del lock: {e}")
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
            })
    return per_club_tm


def _esegui_matching(cur, percorso_input):
    giocatori_tm_per_club_tm = _carica_giocatori_transfermarkt(percorso_input)

    totale_giocatori = sum(len(v) for v in giocatori_tm_per_club_tm.values())
    if totale_giocatori < SOGLIA_MINIMA_GIOCATORI:
        raise DumpNonAffidabile(
            f"Solo {totale_giocatori} giocatori nel dump (attesi almeno {SOGLIA_MINIMA_GIOCATORI})."
        )

    per_id_transfermarkt = {
        g["id_transfermarkt"]: g
        for giocatori in giocatori_tm_per_club_tm.values()
        for g in giocatori
    }

    cur.execute("SELECT club, nome_transfermarkt FROM transfermarkt_mappa_club;")
    mappa_club = {r["club"]: r["nome_transfermarkt"] for r in cur.fetchall()}

    club_mancanti = [nome for nome in mappa_club.values() if nome not in giocatori_tm_per_club_tm]
    if len(club_mancanti) > MASSIMO_CLUB_MANCANTI:
        raise DumpNonAffidabile(f"{len(club_mancanti)} club mancanti dal dump.")

    cur.execute("TRUNCATE transfermarkt_giocatori;")
    for club_tm, giocatori in giocatori_tm_per_club_tm.items():
        for g in giocatori:
            cur.execute(
                """
                INSERT INTO transfermarkt_giocatori
                    (id_transfermarkt, club_tm, nome, cognome, data_nascita, scadenza_contratto)
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (g["id_transfermarkt"], club_tm, g["nome"], g["cognome"],
                 g["data_nascita"], g["scadenza_contratto"]),
            )

    # Refresh dei già mappati: id_transfermarkt non viene mai ricalcolato.
    cur.execute(
        "SELECT id, id_transfermarkt, data_nascita, scadenza_contratto FROM giocatore "
        "WHERE id_transfermarkt IS NOT NULL AND priorita = 1;"
    )
    n_aggiornati = 0
    for g in cur.fetchall():
        aggiornato = per_id_transfermarkt.get(g["id_transfermarkt"])
        if not aggiornato:
            continue
        if (aggiornato["data_nascita"] == g["data_nascita"]
                and aggiornato["scadenza_contratto"] == g["scadenza_contratto"]):
            continue
        cur.execute(
            "UPDATE giocatore SET data_nascita = %s, scadenza_contratto = %s WHERE id = %s;",
            (aggiornato["data_nascita"], aggiornato["scadenza_contratto"], g["id"]),
        )
        n_aggiornati += 1

    cur.execute("SELECT id, nome, club FROM giocatore WHERE id_transfermarkt IS NULL AND priorita = 1;")
    n_auto = n_ambigui = n_non_trovati = 0
    for giocatore in cur.fetchall():
        club_tm = mappa_club.get(giocatore["club"])
        candidati = candidati_esatti(giocatore["nome"], giocatori_tm_per_club_tm.get(club_tm, []))

        if len(candidati) == 1:
            c = candidati[0]
            cur.execute(
                "UPDATE giocatore SET id_transfermarkt = %s, data_nascita = %s, scadenza_contratto = %s WHERE id = %s;",
                (c["id_transfermarkt"], c["data_nascita"], c["scadenza_contratto"], giocatore["id"]),
            )
            n_auto += 1
        elif len(candidati) >= 2:
            cur.execute(
                "UPDATE transfermarkt_giocatori SET id_giocatore = %s WHERE id_transfermarkt = ANY(%s);",
                (giocatore["id"], [c["id_transfermarkt"] for c in candidati]),
            )
            n_ambigui += 1
        else:
            cur.execute(
                "INSERT INTO transfermarkt_giocatori (id_giocatore, id_transfermarkt) VALUES (%s, NULL);",
                (giocatore["id"],),
            )
            n_non_trovati += 1

    print(f"🔄 Aggiornati: {n_aggiornati} | ✅ Nuovi: {n_auto} | ⚠️ Ambigui: {n_ambigui} | ❌ Non trovati: {n_non_trovati}")
