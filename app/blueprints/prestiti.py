import psycopg2
from app import telegram_utils
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.core.db import connessione, resync_sequence
from app.blueprints.user import redirect_gate_chiuso

from app.core.logging import get_logger
from app.core.tempo import formatta_data
from app.domini.calendario import anni_prestito_ammessi
from app.domini.ruoli import pulisci_ruolo
from app.repositories import aste as aste_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import prestiti as prestiti_repo
from app.repositories import squadre as squadre_repo
from app.repositories import vetrina as vetrina_repo

logger = get_logger(__name__)

prestiti_bp = Blueprint('prestiti', __name__, url_prefix='/prestiti')


@prestiti_bp.before_request
def blocca_prestiti_chiuso():
    with connessione() as (conn, cur):
        if not configurazione_repo.mercato_aperto(cur):
            flash("❌ Il mercato scambi è chiuso.", "danger")
            return redirect_gate_chiuso()


@prestiti_bp.route("/prestiti/<nome_squadra>", methods=["GET", "POST"])
def user_prestiti(nome_squadra):
    crediti = 0
    crediti_disponibili = 0
    prestiti = []

    try:
        with connessione(isolamento=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ) as (conn, cur):
            if request.method == "POST":

                # Bottone ANNULLA prestito
                id_prestito_da_annullare = request.form.get("annulla_prestito")
                if id_prestito_da_annullare:
                    prestiti_repo.cambia_stato(cur, id_prestito_da_annullare, 'annullato')
                    conn.commit()
                    flash("✅ Annullata con successo la richiesta di prestito", "success")


                # Bottone ACCETTA prestito
                id_prestito_da_accettare = request.form.get("accetta_prestito")
                if id_prestito_da_accettare:
                    attiva_prestito(id_prestito_da_accettare, nome_squadra)

            
                # Bottone RIFIUTA prestito
                id_prestito_da_rifiutare = request.form.get("rifiuta_prestito")
                if id_prestito_da_rifiutare:
                    prestiti_repo.cambia_stato(cur, id_prestito_da_rifiutare, 'rifiutato')
                    conn.commit()
                    flash("✅ Prestito rifiutato con successo.", "success")
                    telegram_utils.prestito_risposta(conn, id_prestito_da_rifiutare, "Rifiutato")


            crediti = squadre_repo.crediti(cur, nome_squadra)
            offerta_totale = aste_repo.offerta_totale(cur, nome_squadra)
            crediti_disponibili = crediti - offerta_totale

            # Selezione dei prestiti che non sono associati con nessuno scambio
            prestiti_raw = prestiti_repo.in_attesa_per_squadra(cur, nome_squadra)

            prestiti = []

            for p in prestiti_raw:
                prestiti.append({
                    "prestito_id": p["prestito_id"],
                    "giocatore": p["nome"],
                    "ruolo": pulisci_ruolo(p["ruolo"]),
                    "club": p["club"],
                    "squadra_prestante": p["squadra_prestante"],
                    "squadra_ricevente": p["squadra_ricevente"],
                    "stato": p["stato"],
                    "data_inizio": formatta_data(p["data_inizio"]),
                    "data_fine": formatta_data(p["data_fine"]),
                    "note": p["note"],
                    "costo_prestito": p["costo_prestito"],
                    "tipo_prestito": p["tipo_prestito"],
                    "crediti_riscatto": p["crediti_riscatto"]
                })

        
            block_button = False
            prestiti_in_num = giocatori_repo.slot_prestiti_in(cur, nome_squadra)
            if prestiti_in_num >= 2:
                block_button = True


    except Exception:
        logger.exception("❌ Errore durante il caricamento della pagina 'prestiti'")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=0, crediti_disponibili=0, prestiti=[], prestiti_in_num=0, block_button=False)
    

    return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=crediti, crediti_disponibili=crediti_disponibili, prestiti=prestiti, prestiti_in_num=prestiti_in_num, block_button=block_button)


@prestiti_bp.route("/nuovo_prestito/<nome_squadra>", methods=["GET", "POST"])
def nuovo_prestito(nome_squadra):
    conn = None
    cur = None
    crediti = 0
    crediti_disponibili = 0
    giocatori = []
    squadre = []
    anni_scadenza, anno_default_scadenza = anni_prestito_ammessi()
    default_data_fine = f"{anno_default_scadenza}-07-01"

    try:
        with connessione() as (conn, cur):
            if request.method == "POST":
                squadra_prestante = request.form.get("squadra_prestante")
                giocatore_richiesto = request.form.get("giocatore_richiesto")
                data_fine = request.form.get("data_fine") or request.form.get("data_fine_anno")
                note = request.form.get("note", "").strip()
                costo_prestito = request.form.get("costo_prestito", 0)
                tipo_prestito = request.form.get("tipo_prestito", "").strip()
                crediti_riscatto = request.form.get("crediti_riscatto", 0)
            
                # Convert to int with default 0 if empty
                try:
                    costo_prestito = int(costo_prestito) if costo_prestito else 0
                except ValueError:
                    costo_prestito = 0
            
                try:
                    crediti_riscatto = int(crediti_riscatto) if crediti_riscatto else 0
                except ValueError:
                    crediti_riscatto = 0
            
                # Il menù a tendina del frontend non combacia con i valori dell'enum  del database per cui è necessario fare delle modifiche prima dell'INSERT
                if tipo_prestito == 'Secco':
                    crediti_riscatto = 0
                    tipo_prestito = 'secco'

                elif tipo_prestito == 'Con obbligo di riscatto':
                    tipo_prestito = 'obbligo_di_riscatto'

                elif tipo_prestito == 'Con diritto di riscatto':
                    tipo_prestito = 'diritto_di_riscatto'


                if not squadra_prestante or not giocatore_richiesto or not data_fine:
                    flash("❌ Errore: seleziona una squadra, un giocatore e una data di fine prestito.", "danger")
                    return redirect(url_for("prestiti.nuovo_prestito", nome_squadra=nome_squadra))
            
                if len(data_fine) == 4 and data_fine.isdigit():
                    anno_scadenza = int(data_fine)
                else:
                    data_fine_parsed = datetime.strptime(data_fine, "%Y-%m-%d")
                    anno_scadenza = data_fine_parsed.year

                if anno_scadenza not in anni_scadenza:
                    flash("❌ Errore: seleziona uno degli anni di scadenza disponibili.", "danger")
                    return redirect(url_for("prestiti.nuovo_prestito", nome_squadra=nome_squadra))

                data_fine = datetime(anno_scadenza, 7, 1, 23, 59, 59)

                # Riallinea la sequence prima dell'insert: import o restore manuali
                # sul database possono averla lasciata indietro rispetto ai dati, ed
                # e' la causa nota di "duplicate key value violates unique constraint
                # prestito_pkey". La stessa logica scritta a mano qui esisteva gia'
                # in app/core/db.py.
                resync_sequence(conn, 'prestito')

                id_prestito = prestiti_repo.crea(
                    cur, giocatore_richiesto, squadra_prestante, nome_squadra, data_fine,
                    note, costo_prestito, tipo_prestito, crediti_riscatto)
                conn.commit()
                flash("✅ Richiesta inviata correttamente!", "success")
                telegram_utils.nuovo_prestito(conn, id_prestito)
                return redirect(url_for("prestiti.user_prestiti", nome_squadra=nome_squadra))
            


            crediti = squadre_repo.crediti(cur, nome_squadra)
            offerta_totale = aste_repo.offerta_totale(cur, nome_squadra)
            crediti_disponibili = crediti - offerta_totale

            # Selezione dei giocatori
            giocatori_raw = giocatori_repo.prestabili_verso(cur, nome_squadra)

            giocatori = []
            for g in giocatori_raw:
                giocatori.append({
                    "id": g["id"],
                    "nome": g["nome"],
                    "squadra_att": g["squadra_att"],
                    "ruolo": pulisci_ruolo(g["ruolo"]),
                    "club": g["club"]
                })

            # Selezione dei nomi delle squadre, tranne la squadra loggata e Svincolato
            squadre_raw = squadre_repo.nomi_diversi_da(cur, nome_squadra)

            squadre = []
            for s in squadre_raw:
                squadre.append({
                    "nome": s["nome"]
                })

    except Exception:
        logger.exception("❌ Errore durante il caricamento della pagina 'nuovo_prestito'")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=0, crediti_disponibili=0, prestiti=[], prestiti_in_num=0, block_button=False)
    

    return render_template(
        "user_nuovo_prestito.html",
        nome_squadra=nome_squadra,
        crediti=crediti,
        crediti_disponibili=crediti_disponibili,
        giocatori=giocatori,
        squadre=squadre,
        anni_scadenza=anni_scadenza,
        anno_default_scadenza=anno_default_scadenza,
        default_data_fine=default_data_fine,
    )


def attiva_prestito(id_prestito_da_attivare, nome_squadra):

    if not id_prestito_da_attivare:
        flash("❌ Prestito non trovato.", "danger")
        return redirect(url_for("prestiti.user_prestiti", nome_squadra=nome_squadra))
    
    try:
        with connessione() as (conn, cur):
            # Recupero info prestito
            prestito = prestiti_repo.per_id(cur, id_prestito_da_attivare)

            # Cambio di stato
            prestiti_repo.cambia_stato(cur, id_prestito_da_attivare, 'in_corso')
        
            # Modifica info giocatore
            giocatori_repo.assegna_in_prestito(cur, prestito['giocatore'], prestito['squadra_ricevente'])
            vetrina_repo.decadi(cur, prestito['giocatore'])

            # Cancellare altri prestiti per lo stesso giocatore fatti da altre squadre
            prestiti_repo.rifiuta_concorrenti(cur, prestito['squadra_prestante'], prestito['giocatore'])
        
            squadre_repo.sposta_crediti(cur, prestito['squadra_ricevente'], prestito['squadra_prestante'], prestito['costo_prestito'])

            conn.commit()
            flash("✅ Prestito avviato correttamente.", "success")
            telegram_utils.prestito_risposta(conn, id_prestito_da_attivare, "Accettato")


    except Exception:
        logger.exception("❌ Errore durante l'attivazione del prestito")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=0, crediti_disponibili=0, prestiti=[], prestiti_in_num=0, block_button=False)
    
