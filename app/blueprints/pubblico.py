"""
Pagine pubbliche: home, elenco squadre, dashboard di una squadra, listone,
aste, movimenti di mercato, crediti/stadi/slot, regolamento e health check.

Corpo delle funzioni spostato da main.py senza modifiche di logica: cambiano
solo il decoratore (da @app.route a @pubblico_bp.route) e i nomi degli endpoint
nelle url_for, ora prefissati dal blueprint.
"""

from flask import (Blueprint, flash, jsonify, redirect, render_template,
                   send_file, send_from_directory, url_for)

from app import telegram_utils
from app.blueprints.user import format_partecipanti
from app.core.db import connessione

from app.core.logging import get_logger

from app.core.tempo import formatta_data
from app.domini.ruoli import pulisci_ruolo
from app.repositories import albo_oro as albo_oro_repo


from app.repositories import giocatori as giocatori_repo
from app.repositories import movimenti as movimenti_repo
from app.services import dashboard as servizio_dashboard
from app.services import export_excel as export_excel_servizio
from app.services import listone as servizio_listone

logger = get_logger(__name__)

pubblico_bp = Blueprint('pubblico', __name__)


# Pagina principale
@pubblico_bp.route("/")
def home():
    return render_template("index.html")


# Health check endpoint per Render
@pubblico_bp.route("/health")
def health_check():
    try:
        with connessione() as (conn, cur):
            cur.execute("SELECT 1;")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.exception("Health check failed")
        return jsonify({"status": "error", "message": str(e)}), 500


# Schermata squadre con bottoni
@pubblico_bp.route("/squadre")
def squadre():
    try:
        with connessione() as (conn, cur):
            cur.execute('''
                        SELECT nome, username
                        FROM squadra
                        WHERE nome <> 'Svincolato' ORDER BY nome ASC;''')
            squadre = [{"nome": row["nome"], "username": row["username"]} for row in cur.fetchall()]

            return render_template("squadre.html", squadre=squadre)

    except Exception:
        logger.exception("Errore squadre")
        flash("❌ Errore nel recupero squadre.", "danger")
        return redirect(url_for('pubblico.home'))


@pubblico_bp.route("/squadra/<nome_squadra>")
def dashboard_squadra(nome_squadra):
    with connessione() as (conn, cur):
        dati = servizio_dashboard.dati_squadra(cur, nome_squadra)

    if dati is None:
        flash("❌ Squadra non trovata.", "danger")
        return redirect(url_for('pubblico.home'))

    return render_template(
        "dashboard_squadra.html",
        nome_squadra=nome_squadra,
        squadra=[],   # atteso dal template, non usato
        **dati,
    )


# Visualizza tutti gli eventi di mercato con filtri per stagione ed evento
@pubblico_bp.route("/movimenti_mercato")
def movimenti_mercato():

    try:
        with connessione() as (conn, cur):
            mercato_raw = movimenti_repo.tutti(cur)

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

    except Exception:
        logger.exception("Errore movimenti_mercato")
        flash("❌ Errore nel recupero dei movimenti di mercato.", "danger")
        return redirect(url_for('pubblico.home'))


@pubblico_bp.route("/crediti_stadi_slot")
def crediti_stadi_slot():

    try:
        with connessione() as (conn, cur):
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

    except Exception:
        logger.exception("Errore crediti stadi e slot")
        flash("❌ Errore nel caricamento dati stadi.", "danger")
        return redirect(url_for('pubblico.home'))


@pubblico_bp.route("/albo_oro")
def albo_oro():
    with connessione() as (conn, cur):
        righe = albo_oro_repo.leggi(cur)

    return render_template("albo_oro.html", righe=righe)


@pubblico_bp.route("/listone")
def listone():
    with connessione() as (conn, cur):
        dati = servizio_listone.dati_pagina(cur)

    return render_template("listone.html", **dati)


@pubblico_bp.route("/listone/export")
def listone_export():
    with connessione() as (conn, cur):
        giocatori = giocatori_repo.per_export_listone(cur)

    return send_file(
        export_excel_servizio.listone_xlsx(giocatori),
        as_attachment=True,
        download_name="listone_FMM.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@pubblico_bp.route("/aste")
def aste():

    aste = []
    try:
        with connessione() as (conn, cur):
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
                    "ruolo": pulisci_ruolo(a["ruolo"]),
                    "club": a["club"],
                    "squadra_vincente": a["squadra_vincente"],
                    "ultima_offerta": a["ultima_offerta"],
                    "tempo_fine_mostra_interesse": tempo_fine_mostra_interesse,
                    "data_scadenza": data_scadenza,
                    "stato": a["stato"],
                    "partecipanti": partecipanti
                })


    except Exception:
        logger.exception("Errore lista aste generale")
        flash("❌ Errore nella creazione lista aste.", "danger")
        return redirect(url_for('pubblico.home'))


    return render_template("aste.html", aste=aste)


@pubblico_bp.route("/scarica_regolamento")
def vedi_regolamento():
    return send_from_directory('static', 'regolamento.pdf', mimetype='application/pdf', as_attachment=False)


@pubblico_bp.route("/keepalive", methods=["GET", "POST"])
def keepalive():
        telegram_utils.send_message(903944311)
        return render_template("index.html")
