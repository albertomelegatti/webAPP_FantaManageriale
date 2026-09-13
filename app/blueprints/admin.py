import json
import psycopg2
from app import telegram_utils
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.core.db import connessione
from app.domini.matching_transfermarkt import candidati_fuzzy

from app.core.logging import get_logger
from app.core.tempo import formatta_data
from app.domini.ruoli import pulisci_ruolo
from app.repositories import configurazione as configurazione_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import richieste as richieste_repo
from app.repositories import squadre as squadre_repo
from app.repositories import transfermarkt as transfermarkt_repo
from app.repositories import vetrina as vetrina_repo

logger = get_logger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Rotta per area admin
@admin_bp.route("/")
def admin_home():
    return render_template("admin_home.html")

@admin_bp.route("/crediti", methods=["GET", "POST"])
def admin_crediti():
    squadre = []
    
    with connessione(isolamento=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ) as (conn, cur):
        if request.method == "POST":
            i = 0
            max_squadre = 100  # Protezione contro loop infinito
            while f"squadre[{i}][nome]" in request.form and i < max_squadre:
                nome = request.form.get(f"squadre[{i}][nome]")
                nuovo_credito = request.form.get(f"squadre[{i}][nuovo_credito]")
                if nome and nuovo_credito:
                    try:
                        nuovo_credito = int(nuovo_credito)
                        squadre_repo.imposta_crediti(cur, nome, nuovo_credito)
                    except ValueError:
                        logger.warning("Valore crediti non valido per la squadra %s", nome)
                i += 1
            conn.commit()
            flash("✅ Tutti i crediti sono stati aggiornati con successo!", "success")
            return redirect(url_for("admin.admin_crediti"))


        squadre = squadre_repo.nomi_e_crediti(cur)

    return render_template("admin_crediti.html", squadre=squadre)


@admin_bp.route("/chiusura_mercato_aste", methods=["GET", "POST"])
def admin_chiusura_mercato_aste():
    stato_gate = None

    with connessione() as (conn, cur):
        if request.method == "POST":
            mercato_chiusura_raw = request.form.get("mercato_chiusura") or None
            aste_chiusura_raw = request.form.get("aste_chiusura") or None
            u21_threshold_year_raw = request.form.get("u21_threshold_year") or None

            def parse_data(data_raw):
                if not data_raw:
                    return None
                return datetime.strptime(data_raw, "%Y-%m-%d").date()

            try:
                mercato_chiusura = parse_data(mercato_chiusura_raw)
                aste_chiusura = parse_data(aste_chiusura_raw)
            except ValueError:
                flash("❌ Data non valida.", "danger")
                return redirect(url_for("admin.admin_chiusura_mercato_aste"))

            try:
                u21_threshold_year = int(u21_threshold_year_raw) if u21_threshold_year_raw else None
            except ValueError:
                flash("❌ Anno soglia U21 non valido.", "danger")
                return redirect(url_for("admin.admin_chiusura_mercato_aste"))

            configurazione_repo.aggiorna_chiusure(cur, mercato_chiusura, aste_chiusura, u21_threshold_year)
            conn.commit()
            flash("✅ Impostazioni di chiusura aggiornate con successo.", "success")
            return redirect(url_for("admin.admin_chiusura_mercato_aste"))

        stato_gate = configurazione_repo.stato_gate(cur)

    return render_template("admin_chiusura_mercato_aste.html", stato_gate=stato_gate)


@admin_bp.route("/invia_comunicazione", methods=["GET", "POST"])
def invia_comunicazione():
    squadre = []

    with connessione() as (conn, cur):
        if request.method == "POST":
            text_to_send = request.form.get("text_to_send", "").strip()
        
            if not text_to_send:
                flash("❌ Il messaggio non può essere vuoto.", "warning")
                return redirect(url_for("admin.invia_comunicazione"))
            telegram_utils.send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
        
            flash(f"✅ Messaggi inviati a {len(squadre)} squadre.", "success")

    return render_template("admin_comunicazione.html", squadre=squadre)


@admin_bp.route("/richiesta/modifica/contratto", methods=["GET", "POST"])
def richiesta_modifica_contratto():
    richieste = []

    with connessione() as (conn, cur):
        if request.method == "POST":

            # RIFIUTA RICHIESTA DI MODIFICA CONTRATTO
            if request.form.get("rifiuta_richiesta"):
                id_richiesta = request.form.get("id_richiesta")

                # Aggiornamento stato richiesta
                richieste_repo.rifiuta(cur, id_richiesta)
                conn.commit()
                flash("✅ Richiesta di modifica contratto rifiutata con successo.", "success")
                telegram_utils.richiesta_modifica_contratto_risposta(conn, id_richiesta, "Rifiutato")


            # ACCETTA RICHIESTA DI MODIFICA CONTRATTO
            if request.form.get("accetta_richiesta"):
                id_richiesta = request.form.get("id_richiesta")

                # Aggiornamento stato richiesta
                richieste_repo.accetta(cur, id_richiesta)

                # Recupero informazioni sulla richiesta
                row = richieste_repo.dettaglio(cur, id_richiesta)
                id_giocatore = row['giocatore']
                nuovo_contratto = row['contratto_richiesto']
                crediti_richiesti = row['crediti_richiesti']
                squadra_richiedente = row['squadra_richiedente']

                # Logica per aggiornare squadra_attuale e detentore_cartellino
                if nuovo_contratto == 'Svincolato':
                    # Squadra attuale e detentore cartellino vanno a "Svincolato"
                    giocatori_repo.svincola(cur, id_giocatore, nuovo_contratto)
                    vetrina_repo.decadi(cur, id_giocatore)
                elif nuovo_contratto == 'Prestito Reale':
                    # Solo la squadra attuale va a "Svincolato"
                    giocatori_repo.manda_in_prestito_reale(cur, id_giocatore, nuovo_contratto)
                    vetrina_repo.decadi(cur, id_giocatore)
                elif nuovo_contratto == 'Indeterminato':
                    # La squadra attuale torna al detentore cartellino
                    giocatori_repo.assegna_a_squadra(cur, id_giocatore, nuovo_contratto, squadra_richiedente)
                else:
                    # Per altri tipi di contratto, aggiorna solo il tipo di contratto
                    giocatori_repo.cambia_tipo_contratto(cur, id_giocatore, nuovo_contratto)
                # "Indeterminato" e "Hold" non fanno decadere la vetrina: il giocatore
                # resta alla squadra richiedente, non è un vero movimento di mercato.

                # Aggiornamento crediti squadra: la modifica contratto assegna i crediti richiesti
                squadre_repo.aggiungi_crediti(cur, squadra_richiedente, crediti_richiesti)


                conn.commit()
                flash("✅ Richiesta di modifica contratto accettata con successo.", "success")
                telegram_utils.richiesta_modifica_contratto_risposta(conn, id_richiesta, "Accettato")
                return redirect(url_for("admin.richiesta_modifica_contratto"))


        richieste = []
        for r in richieste_repo.elenco(cur):
            richieste.append({
                "id": r["id"],
                "nome_giocatore": r["nome"],
                "ruolo": pulisci_ruolo(r["ruolo"]),
                "club": r["club"],
                "contratto_attuale": r["tipo_contratto"],
                "contratto_richiesto": r["contratto_richiesto"],
                "squadra_richiedente": r["squadra_richiedente"],
                "crediti_richiesti": r["crediti_richiesti"],
                "messaggio": r["messaggio"],
                "data": formatta_data(r["data"]),
                "stato": r["stato"]
            })

    return render_template("admin_richiesta_modifica_contratto.html", richieste=richieste)


@admin_bp.route("/verifica_corrispondenze_giocatori", methods=["GET", "POST"])
def admin_verifica_corrispondenze():
    giocatori_da_rivedere = []

    with connessione() as (conn, cur):
        if request.method == "POST":
            corrispondenze_data_raw = request.form.get("corrispondenze_data", "")

            try:
                risoluzioni = json.loads(corrispondenze_data_raw) if corrispondenze_data_raw else []
            except (ValueError, TypeError):
                flash("❌ Dati inviati non validi, ricarica la pagina e riprova.", "danger")
                return redirect(url_for("admin.admin_verifica_corrispondenze"))

            id_giocatori_in_coda = transfermarkt_repo.id_giocatori_in_coda(cur)

            def rimuovi_dalla_coda(id_giocatore):
                transfermarkt_repo.rimuovi_dalla_coda(cur, id_giocatore)

            n_selezioni_non_valide = 0

            for risoluzione in risoluzioni:
                try:
                    id_giocatore = int(risoluzione.get("id_giocatore"))
                except (TypeError, ValueError):
                    continue
                if id_giocatore not in id_giocatori_in_coda:
                    continue

                valore_scelto = str(risoluzione.get("id_transfermarkt") or "").strip()
                if not valore_scelto:
                    continue

                if valore_scelto == "nessuna":
                    # Dismissione volontaria: nessun dato da salvare su giocatore.
                    rimuovi_dalla_coda(id_giocatore)
                    continue

                candidato = None

                if valore_scelto.startswith("fuzzy:"):
                    # Suggerimento fuzzy: non era marcato come candidato, va cercato
                    # nella cache solo ora che l'admin lo conferma.
                    id_tm_fuzzy_raw = valore_scelto.split(":", 1)[1]
                    if id_tm_fuzzy_raw.isdigit():
                        candidato = transfermarkt_repo.candidato_per_id_transfermarkt(cur, id_tm_fuzzy_raw)

                elif valore_scelto.isdigit():
                    candidato = transfermarkt_repo.candidato_per_giocatore(cur, id_giocatore, valore_scelto)

                if not candidato:
                    # La selezione non è (più) valida, es. la cache è stata rigenerata da
                    # un nuovo run dello script mentre la pagina era aperta: non tocchiamo
                    # la coda, resta lì per essere rivista con dati aggiornati.
                    n_selezioni_non_valide += 1
                    continue

                transfermarkt_repo.conferma_abbinamento(cur, id_giocatore, candidato)
                rimuovi_dalla_coda(id_giocatore)

            conn.commit()
            if n_selezioni_non_valide:
                flash(
                    f"⚠️ {n_selezioni_non_valide} selezioni non erano più valide (dati aggiornati nel frattempo) "
                    "e sono rimaste in coda: ricontrollale.",
                    "warning",
                )
            flash("✅ Corrispondenze aggiornate con successo.", "success")
            return redirect(url_for("admin.admin_verifica_corrispondenze"))

        righe = transfermarkt_repo.da_rivedere(cur)

        per_giocatore = {}
        for r in righe:
            entry = per_giocatore.setdefault(r["id_giocatore"], {
                "id": r["id_giocatore"],
                "nome": r["nome"],
                "club": r["club"],
                "ruolo": pulisci_ruolo(r["ruolo"]),
                "candidati": [],
                "suggerimenti": [],
            })
            if r["id_transfermarkt"] is not None:
                entry["candidati"].append({
                    "id_transfermarkt": r["id_transfermarkt"],
                    "nome_completo": f"{r['nome_tm']} {r['cognome_tm']}".strip(),
                    "club": r["club_tm"],
                    "data_nascita": r["data_nascita"].strftime("%d/%m/%Y") if r["data_nascita"] else None,
                })

        # Per i giocatori "non trovati" dal match esatto (nessun candidato reale, solo
        # la riga sintetica) calcoliamo qui, al volo, dei suggerimenti fuzzy dall'ultimo
        # dump scaricato: non vengono mai marcati come candidati in transfermarkt_giocatori,
        # compaiono solo in questa pagina finché l'admin non ne conferma uno.
        non_trovati = [g for g in per_giocatore.values() if not g["candidati"]]
        if non_trovati:
            mappa_club = transfermarkt_repo.mappa_club(cur)

            for g in non_trovati:
                club_tm = mappa_club.get(g["club"])
                if not club_tm:
                    continue
                rosa_tm = transfermarkt_repo.rosa_per_club_tm(cur, club_tm)
                for c in candidati_fuzzy(g["nome"], rosa_tm):
                    g["suggerimenti"].append({
                        "id_transfermarkt": c["id_transfermarkt"],
                        "nome_completo": f"{c['nome']} {c['cognome']}".strip(),
                        "club": club_tm,
                        "data_nascita": c["data_nascita"].strftime("%d/%m/%Y") if c["data_nascita"] else None,
                    })

        for g in per_giocatore.values():
            if g["candidati"]:
                g["categoria"] = "ambiguo"
            elif g["suggerimenti"]:
                g["categoria"] = "suggerito"
            else:
                g["categoria"] = "non_trovato"

        # Le righe con qualcosa da valutare (ambigue o con suggerimento) vanno in cima:
        # sono le uniche davvero actionable, i "non trovati" senza suggerimento sono la
        # maggioranza silenziosa e non serve che scorrano prima nella lista.
        ordine_categoria = {"ambiguo": 0, "suggerito": 1, "non_trovato": 2}
        giocatori_da_rivedere = sorted(
            per_giocatore.values(),
            key=lambda g: (ordine_categoria[g["categoria"]], g["nome"]),
        )
        conteggi = {
            "ambiguo": sum(1 for g in giocatori_da_rivedere if g["categoria"] == "ambiguo"),
            "suggerito": sum(1 for g in giocatori_da_rivedere if g["categoria"] == "suggerito"),
            "non_trovato": sum(1 for g in giocatori_da_rivedere if g["categoria"] == "non_trovato"),
        }

    return render_template("admin_verifica_corrispondenze.html", giocatori=giocatori_da_rivedere, conteggi=conteggi)