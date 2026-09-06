"""
Pagine pubbliche: home, elenco squadre, dashboard di una squadra, listone,
aste, movimenti di mercato, crediti/stadi/slot, regolamento e health check.

Corpo delle funzioni spostato da main.py senza modifiche di logica: cambiano
solo il decoratore (da @app.route a @pubblico_bp.route) e i nomi degli endpoint
nelle url_for, ora prefissati dal blueprint.
"""

from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   send_from_directory, url_for)
from psycopg2.extras import RealDictCursor

from app import telegram_utils
from app.blueprints.user import format_partecipanti, formatta_data
from app.core.db import get_connection, release_connection
from app.queries import (formatta_data_nascita_con_eta,
                         formatta_scadenza_contratto, get_slot_aste,
                         get_slot_giocatori, ruolo_base_sort_key,
                         ruolo_sort_key)

pubblico_bp = Blueprint('pubblico', __name__)


# Pagina principale
@pubblico_bp.route("/")
def home():
    return render_template("index.html")


# Health check endpoint per Render
@pubblico_bp.route("/health")
def health_check():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        release_connection(conn, cur)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        print(f"Health check failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Schermata squadre con bottoni
@pubblico_bp.route("/squadre")
def squadre():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
                    SELECT nome, username
                    FROM squadra
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre = [{"nome": row["nome"], "username": row["username"]} for row in cur.fetchall()]

        return render_template("squadre.html", squadre=squadre)

    except Exception as e:
        print("Errore squadre:", e)
        flash("❌ Errore nel recupero squadre.", "danger")
        return redirect(url_for('pubblico.home'))

    finally:
        release_connection(conn, cur)


@pubblico_bp.route("/squadra/<nome_squadra>")
def dashboard_squadra(nome_squadra):

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # STADIO
        cur.execute('''
                    SELECT nome, proprietario, livello
                    FROM stadio
                    WHERE proprietario = %s;
        ''', (nome_squadra,))
        stadio = cur.fetchone()

        # CREDITI
        cur.execute('''
                    SELECT username, crediti
                    FROM squadra
                    WHERE nome = %s;
        ''', (nome_squadra,))
        squadra_raw = cur.fetchone()
        username = squadra_raw["username"]
        crediti = squadra_raw["crediti"]

        # CONTEGGIO SLOT GIOCATORI E ASTE (slot_occupati = somma dei due, evita di ricalcolare slot_giocatori due volte)
        slot_giocatori = get_slot_giocatori(conn, nome_squadra)
        slot_aste = get_slot_aste(conn, nome_squadra)
        slot_occupati = slot_giocatori + slot_aste

        # ROSA
        rosa = []
        cur.execute('''
                    SELECT g.nome, g.tipo_contratto, g.ruolo, g.quot_att_mantra, g.costo, g.club,
                           g.squadra_att, g.detentore_cartellino, g.data_nascita, g.scadenza_contratto,
                           s.username AS squadra_username, d.username AS detentore_username
                    FROM giocatore g
                    LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
                    LEFT JOIN squadra d ON d.nome = g.detentore_cartellino AND g.detentore_cartellino <> 'Svincolato'
                    WHERE g.squadra_att = %s
                        AND g.tipo_contratto <> 'Primavera';
        ''' , (nome_squadra,))
        rosa_raw = cur.fetchall()

        for g in rosa_raw:
            ruolo = g['ruolo'].strip("{}")
            rosa.append({
                "nome": g['nome'],
                "tipo_contratto": g['tipo_contratto'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra'],
                "costo": g['costo'],
                "club": g['club'],
                "squadra_att": g['squadra_att'],
                "squadra_username": g['squadra_username'],
                "detentore_cartellino": g['detentore_cartellino'],
                "detentore_username": g['detentore_username'],
                "data_nascita": formatta_data_nascita_con_eta(g['data_nascita']) or "Non sincronizzata",
                "scadenza_contratto_reale": formatta_scadenza_contratto(g['scadenza_contratto']) or "Non sincronizzata",
            })

        rosa.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        # PRIMAVERA
        primavera = []
        cur.execute('''
                    SELECT nome, tipo_contratto, ruolo, quot_att_mantra
                    FROM giocatore
                    WHERE squadra_att = %s
                        AND tipo_contratto = 'Primavera';
        ''' , (nome_squadra,))
        primavera_raw = cur.fetchall()

        for g in primavera_raw:
            ruolo = g['ruolo'].strip("{}")
            primavera.append({
                "nome": g['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra']
            })

        primavera.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        # PRESTITI IN (prestiti_in_num ricavato da len(), evita una COUNT separata con la stessa WHERE)
        prestiti_in = []
        cur.execute('''
                    SELECT nome, ruolo, quot_att_mantra, detentore_cartellino
                    FROM giocatore
                    WHERE squadra_att = %s
                        AND tipo_contratto = 'Fanta-Prestito';
        ''', (nome_squadra,))
        prestiti_in_raw = cur.fetchall()

        for g in prestiti_in_raw:
            ruolo = g['ruolo'].strip("{}")
            prestiti_in.append({
                "nome": g['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra'],
                "detentore_cartellino": g["detentore_cartellino"]
            })

        prestiti_in.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        prestiti_in_num = len(prestiti_in)

        # DRAFT - pick detenute dalla squadra
        draft_pick = []
        cur.execute('''
                    SELECT d.detentore_originale, d.anno, d.numero, g.nome AS giocatore_scelto
                    FROM draft d
                    LEFT JOIN giocatore g
                        ON d.id_giocatore_scelto = g.id
                    WHERE d.detentore_att = %s
                    ORDER BY d.anno, d.numero;
        ''', (nome_squadra,))
        draft_pick_raw = cur.fetchall()

        for p in draft_pick_raw:
            anno = p['anno'].year if hasattr(p['anno'], 'year') else p['anno']
            draft_pick.append({
                "detentore_originale": p["detentore_originale"],
                "anno": anno,
                "numero": p["numero"],
                "giocatore_scelto": p["giocatore_scelto"] or "—"
            })

        # PRESTITI OUT
        prestiti_out = []
        cur.execute('''
                    SELECT nome, ruolo, quot_att_mantra, squadra_att
                    FROM giocatore
                    WHERE detentore_cartellino = %s
                        AND tipo_contratto in ('Fanta-Prestito', 'Prestito Reale');
        ''', (nome_squadra,))
        prestiti_out_raw = cur.fetchall()

        for g in prestiti_out_raw:
            ruolo = g['ruolo'].strip("{}")
            prestiti_out.append({
                "nome": g['nome'],
                "ruolo": ruolo,
                "quot_att_mantra": g['quot_att_mantra'],
                "squadra_att": g['squadra_att']
            })

        prestiti_out.sort(key=lambda g: ruolo_sort_key(g['ruolo']))

        # MOVIMENTI DI MERCATO
        mercato = []
        cur.execute('''
                SELECT data, evento, stagione
                FROM movimenti_squadra
                WHERE evento ILIKE %s and evento not ilike '%%🏷️ ASTA%%'
                ORDER BY data DESC;
        ''', (f'%{nome_squadra}%',))
        mercato_raw = cur.fetchall()

        for m in mercato_raw:
            mercato.append({
                "data": m['data'],
                "evento": m['evento'],
                "stagione": m['stagione']
            })

        return render_template(
            "dashboard_squadra.html",
            nome_squadra=nome_squadra,
            rosa=rosa,
            primavera=primavera,
            prestiti_in=prestiti_in,
            prestiti_in_num=prestiti_in_num,
            draft_pick=draft_pick,
            prestiti_out=prestiti_out,
            stadio=stadio,
            username=username,
            crediti=crediti,
            squadra=[],
            slot_occupati=slot_occupati,
            slot_giocatori=slot_giocatori,
            mercato=mercato
        )

    except Exception as e:
        print("Errore dashboard Squadra:", e)
        flash("❌ Errore nel caricamento della squadra.", "danger")
        return redirect(url_for('pubblico.home'))

    finally:
        release_connection(conn, cur)


# Visualizza tutti gli eventi di mercato con filtri per stagione ed evento
@pubblico_bp.route("/movimenti_mercato")
def movimenti_mercato():

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupera tutti gli eventi di mercato
        cur.execute('''
                    SELECT data, evento, stagione
                    FROM movimenti_squadra
                    WHERE evento NOT ILIKE '%%🏷️ ASTA%%'
                    ORDER BY data DESC;
        ''')
        mercato_raw = cur.fetchall()

        mercato = []
        for m in mercato_raw:
            mercato.append({
                "data": m['data'],
                "evento": m['evento'],
                "stagione": m['stagione']
            })

        # Recupera tutte le squadre (eccetto Svincolato)
        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome <> 'Svincolato'
                    ORDER BY nome ASC;
        ''')
        squadre_raw = cur.fetchall()
        squadre = [row['nome'] for row in squadre_raw]

        return render_template(
            "movimenti_mercato.html",
            mercato=mercato,
            squadre=squadre
        )

    except Exception as e:
        print("Errore movimenti_mercato:", e)
        flash("❌ Errore nel recupero dei movimenti di mercato.", "danger")
        return redirect(url_for('pubblico.home'))

    finally:
        release_connection(conn, cur)


@pubblico_bp.route("/crediti_stadi_slot")
def crediti_stadi_slot():

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # CREDITI
        cur.execute('''
                    SELECT nome, crediti
                    FROM squadra
                    WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
        squadre_raw = cur.fetchall()
        squadre = [{"nome": c['nome'], "crediti": c['crediti']} for c in squadre_raw]

        # STADIO
        cur.execute('''
                    SELECT nome, proprietario, livello
                    FROM stadio ORDER BY proprietario ASC;''')
        stadi_raw = cur.fetchall()
        stadi = []
        for s in stadi_raw:
            livello = s['livello']
            bonus = [0,4,8,14,18,25,30,39,44][livello] if livello <= 8 else 0
            stadi.append({
                "proprietario": s['proprietario'],
                "nome": s['nome'],
                "livello": livello,
                "crediti_annuali": bonus
            })

        # CONTEGGIO SLOT OCCUPATI E IN PRESTITO
        cur.execute('''
                    SELECT squadra_att, COUNT(id) AS slot_occupati
                    FROM giocatore
                    WHERE tipo_contratto IN ('Hold', 'Indeterminato')
                    GROUP BY squadra_att;''')
        slot_raw = cur.fetchall()

        cur.execute('''
                    SELECT squadra_att, COUNT(id) AS slot_in_prestito
                    FROM giocatore
                    WHERE tipo_contratto = 'Fanta-Prestito'
                    GROUP BY squadra_att;''')
        slot_prestito_raw = cur.fetchall()
        slot_prestito_dict = {s["squadra_att"]: s["slot_in_prestito"] for s in slot_prestito_raw}

        slot = []
        for s in slot_raw:
            slot.append({
                "squadra_att": s["squadra_att"],
                "slot_occupati": s["slot_occupati"],
                "slot_in_prestito": slot_prestito_dict.get(s["squadra_att"], 0)
            })


        return render_template("crediti_stadi_slot.html", stadi=stadi, squadre=squadre, slot=slot)

    except Exception as e:
        print("Errore crediti stadi e slot:", e)
        flash("❌ Errore nel caricamento dati stadi.", "danger")
        return redirect(url_for('pubblico.home'))

    finally:
        release_connection(conn, cur)


@pubblico_bp.route("/listone")
def listone():
    conn = None
    cur = None
    giocatori = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("""
            SELECT g.nome, g.ruolo, g.club, g.squadra_att, g.tipo_contratto, g.quot_att_mantra, g.costo,
                   g.detentore_cartellino, s.username AS squadra_username, d.username AS detentore_username,
                   g.data_nascita, g.scadenza_contratto
            FROM giocatore g
            LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
            LEFT JOIN squadra d ON d.nome = g.detentore_cartellino AND g.detentore_cartellino <> 'Svincolato'
            WHERE g.priorita = 1
            ORDER BY g.quot_att_mantra DESC;
        """)
        giocatori = [
            {
                "nome": g["nome"],
                "ruolo": (g["ruolo"] or "").strip("{}"),
                "club": g["club"],
                "squadra_att": g["squadra_att"],
                "squadra_username": g["squadra_username"],
                "detentore_cartellino": g["detentore_cartellino"],
                "detentore_username": g["detentore_username"],
                "tipo_contratto": g["tipo_contratto"],
                "quotazione": g["quot_att_mantra"],
                "costo": g["costo"],
                "data_nascita": formatta_data_nascita_con_eta(g["data_nascita"]) or "Non sincronizzata",
                "scadenza_contratto_reale": formatta_scadenza_contratto(g["scadenza_contratto"]) or "Non sincronizzata",
            }
            for g in cur.fetchall()
        ]

    except Exception as e:
        print("Errore caricamento listone:", e)
        flash("❌ Errore durante il caricamento del listone.", "danger")

    finally:
        release_connection(conn, cur)

    ruoli_base = set()
    for g in giocatori:
        for token in g["ruolo"].split(","):
            token = token.strip()
            if token:
                ruoli_base.add(token)
    ruoli_disponibili = sorted(ruoli_base, key=ruolo_base_sort_key)

    club_disponibili = sorted({g["club"] for g in giocatori if g["club"]})
    squadre_disponibili = sorted({g["squadra_att"] for g in giocatori if g["squadra_att"]})
    contratti_disponibili = sorted({g["tipo_contratto"] for g in giocatori if g["tipo_contratto"]})

    return render_template("listone.html",
                            giocatori=giocatori,
                            ruoli_disponibili=ruoli_disponibili,
                            club_disponibili=club_disponibili,
                            squadre_disponibili=squadre_disponibili,
                            contratti_disponibili=contratti_disponibili)


@pubblico_bp.route("/aste")
def aste():

    conn = None
    cur = None
    aste = []
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory = RealDictCursor)

        cur.execute('''
                    SELECT g.nome, g.ruolo, g.club, a.squadra_vincente, a.ultima_offerta, a.tempo_fine_asta, a.tempo_fine_mostra_interesse, a.stato, a.partecipanti
                    FROM asta a
                    JOIN giocatore g ON a.giocatore = g.id
                    ORDER BY a.tempo_fine_asta DESC;''')
        aste_raw = cur.fetchall()

        for a in aste_raw:

            data_scadenza = formatta_data(a["tempo_fine_asta"])
            tempo_fine_mostra_interesse = formatta_data(a["tempo_fine_mostra_interesse"])

            partecipanti = format_partecipanti(a["partecipanti"])

            aste.append({
                "giocatore": a["nome"],
                "ruolo": a["ruolo"].strip("{}"),
                "club": a["club"],
                "squadra_vincente": a["squadra_vincente"],
                "ultima_offerta": a["ultima_offerta"],
                "tempo_fine_mostra_interesse": tempo_fine_mostra_interesse,
                "data_scadenza": data_scadenza,
                "stato": a["stato"],
                "partecipanti": partecipanti
            })


    except Exception as e:
        print("Errore lista aste generale:", e)
        flash("❌ Errore nella creazione lista aste.", "danger")
        return redirect(url_for('pubblico.home'))

    finally:
        release_connection(conn, cur)

    return render_template("aste.html", aste=aste)


@pubblico_bp.route("/scarica_regolamento")
def vedi_regolamento():
    return send_from_directory('static', 'regolamento.pdf', mimetype='application/pdf', as_attachment=False)


@pubblico_bp.route("/keepalive", methods=["GET", "POST"])
def keepalive():
        telegram_utils.send_message(903944311)
        return render_template("index.html")
