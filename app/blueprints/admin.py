import json
import secrets
import psycopg2
from app import telegram_utils
from datetime import date, datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request, session
from app.core.db import connessione
from app.core.formato import url_campioncino
from app.domini.matching_transfermarkt import candidati_fuzzy
from app.core.errori import ErroreDominio
from app.domini import albo_oro as dominio_albo_oro
from app.domini.movimenti import squadre_citate

from app.core.logging import get_logger
from app.core.tempo import formatta_data, oggi
from app.domini.ruoli import pulisci_ruolo
from app.blueprints.draft import annuncia as annuncia_draft
from app.repositories import albo_oro as albo_oro_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import draft as draft_repo
from app.repositories import draft_sessione as draft_sessione_repo
from app.repositories import fantacalcio as fantacalcio_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import richieste as richieste_repo
from app.repositories import squadre as squadre_repo
from app.repositories import stadio as stadio_repo
from app.repositories import storico_rosa as storico_rosa_repo
from app.repositories import transfermarkt as transfermarkt_repo
from app.repositories import vetrina as vetrina_repo
from app.services import draft_live as servizio_draft
from app.services import fantacalcio as servizio_fantacalcio
from app.services.crediti_stadi_slot import RENDITA_STADIO, rendite_da_accreditare, rendite_in_uso

logger = get_logger(__name__)

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def richiedi_admin():
    """Ogni pagina di /admin e' riservata all'admin: senza il flag di sessione
    impostato dal login (vedi auth.py) si torna alla home."""
    if not session.get("is_admin"):
        return redirect(url_for("public.home"))


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
            # Testo libero digitato dall'admin: nessuna squadra strutturata a
            # monte, quindi si cercano i nomi citati - la stessa euristica per
            # sottostringa che prima leggeva il legame movimento-squadra a ogni
            # lettura, applicata qui una volta sola in scrittura.
            squadre_citate_nel_messaggio = squadre_citate(text_to_send, squadre_repo.nomi(cur))
            telegram_utils.send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send,
                                        squadre_evento=squadre_citate_nel_messaggio)
        
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


@admin_bp.route("/sincronizza_campioncini")
def admin_sincronizza_campioncini():
    with connessione() as (conn, cur):
        riepilogo = servizio_fantacalcio.sincronizza(cur)
        conn.commit()

    flash(
        f"✅ Sincronizzazione completata: {riepilogo['auto']} abbinati automaticamente, "
        f"{riepilogo['fuori_listone']} fuori listone (per nome e club), "
        f"{riepilogo['recuperati']} prima segnati senza corrispondenza, "
        f"{riepilogo['id_aggiornati']} id corretti, "
        f"{riepilogo['ambigui']} ambigui e {riepilogo['non_trovati']} non trovati da rivedere.",
        "success",
    )
    return redirect(url_for("admin.admin_verifica_campioncini"))


@admin_bp.route("/verifica_campioncini", methods=["GET", "POST"])
def admin_verifica_campioncini():
    giocatori_da_rivedere = []

    with connessione() as (conn, cur):
        if request.method == "POST":
            corrispondenze_data_raw = request.form.get("corrispondenze_data", "")

            try:
                risoluzioni = json.loads(corrispondenze_data_raw) if corrispondenze_data_raw else []
            except (ValueError, TypeError):
                flash("❌ Dati inviati non validi, ricarica la pagina e riprova.", "danger")
                return redirect(url_for("admin.admin_verifica_campioncini"))

            id_giocatori_in_coda = fantacalcio_repo.id_giocatori_in_coda(cur)
            n_selezioni_non_valide = 0

            for risoluzione in risoluzioni:
                try:
                    id_giocatore = int(risoluzione.get("id_giocatore"))
                except (TypeError, ValueError):
                    continue
                if id_giocatore not in id_giocatori_in_coda:
                    continue

                valore_scelto = str(risoluzione.get("id_fantacalcio") or "").strip()
                if not valore_scelto:
                    continue

                if valore_scelto == "nessuna":
                    fantacalcio_repo.segna_nessuna_corrispondenza(cur, id_giocatore)
                    fantacalcio_repo.rimuovi_dalla_coda(cur, id_giocatore)
                    continue

                if not valore_scelto.isdigit() or not fantacalcio_repo.esiste_in_cache(cur, int(valore_scelto)):
                    # Selezione non (più) valida, es. una sincronizzazione ha
                    # rigenerato la cache mentre la pagina era aperta: non si
                    # tocca la coda, resta li' per essere rivista con dati
                    # aggiornati invece di scrivere un id inventato.
                    n_selezioni_non_valide += 1
                    continue

                fantacalcio_repo.conferma_abbinamento(cur, id_giocatore, int(valore_scelto))
                fantacalcio_repo.rimuovi_dalla_coda(cur, id_giocatore)

            conn.commit()
            if n_selezioni_non_valide:
                flash(f"⚠️ {n_selezioni_non_valide} selezioni non erano valide e sono rimaste in coda.", "warning")
            flash("✅ Corrispondenze aggiornate con successo.", "success")
            return redirect(url_for("admin.admin_verifica_campioncini"))

        giocatori_da_rivedere = servizio_fantacalcio.dati_revisione(cur)
        conteggi = {
            "ambiguo": sum(1 for g in giocatori_da_rivedere if g["categoria"] == "ambiguo"),
            "non_trovato": sum(1 for g in giocatori_da_rivedere if g["categoria"] == "non_trovato"),
        }

    return render_template("admin_verifica_campioncini.html", giocatori=giocatori_da_rivedere, conteggi=conteggi)


@admin_bp.route("/arrivi_in_rosa", methods=["GET", "POST"])
def admin_arrivi_in_rosa():
    """Date di arrivo in rosa che non si sono potute ricostruire dallo storico
    di aste, scambi e riscatti: le completa l'admin, una riga alla volta o
    tutte quelle visibili con la stessa data."""
    with connessione() as (conn, cur):
        if request.method == "POST":
            n_salvate = 0
            n_non_valide = 0
            for chiave, valore in request.form.items():
                if not chiave.startswith("dal_") or not valore.strip():
                    continue
                try:
                    id_riga = int(chiave.removeprefix("dal_"))
                    data_arrivo = date.fromisoformat(valore.strip())
                except ValueError:
                    n_non_valide += 1
                    continue
                if data_arrivo > oggi():
                    n_non_valide += 1
                    continue
                if storico_rosa_repo.imposta_arrivo(cur, id_riga, data_arrivo):
                    n_salvate += 1

            conn.commit()
            if n_non_valide:
                flash(f"⚠️ {n_non_valide} date non valide (o nel futuro) non sono state salvate.", "warning")
            flash(f"✅ {n_salvate} date di arrivo salvate.", "success")
            return redirect(url_for("admin.admin_arrivi_in_rosa"))

        righe = storico_rosa_repo.arrivi_da_completare(cur)

    for riga in righe:
        riga["ruolo"] = pulisci_ruolo(riga["ruolo"])
        for s in riga["suggerimenti"]:
            s["data_iso"] = s["data"]
            s["data"] = date.fromisoformat(s["data"]).strftime("%d/%m/%Y")

    squadre = sorted({r["squadra"] for r in righe})
    return render_template("admin_arrivi_in_rosa.html", righe=righe, squadre=squadre, oggi=oggi().isoformat())


@admin_bp.route("/albo_oro", methods=["GET", "POST"])
def admin_albo_oro():
    """Albo d'oro di una stagione come sulla pagina pubblica, ma compilabile.

    Registra soltanto lo storico: i crediti indicati NON vengono accreditati
    alle squadre (si fa da Gestione Crediti). Il salvataggio riscrive tutta
    la stagione con quello che c'e' nella griglia.
    """
    with connessione() as (conn, cur):
        squadre = squadre_repo.nomi_e_username(cur)
        nomi = [s["nome"] for s in squadre]

        if request.method == "POST":
            try:
                stagione = dominio_albo_oro.stagione_valida(request.form.get("stagione"))
                righe = dominio_albo_oro.piazzamenti_da_form(request.form, nomi)
                if not righe and albo_oro_repo.per_stagione(cur, stagione):
                    raise ErroreDominio(
                        "❌ Nessun piazzamento compilato: salvataggio annullato per non "
                        "svuotare la stagione per errore.")
                albo_oro_repo.sostituisci_stagione(cur, stagione, righe)
                conn.commit()
                flash(f"✅ Albo d'oro {stagione} salvato ({len(righe)} piazzamenti).", "success")
                return redirect(url_for("admin.admin_albo_oro", stagione=stagione))
            except ErroreDominio as e:
                conn.rollback()
                flash(e.messaggio_utente, "danger")
                return redirect(url_for("admin.admin_albo_oro",
                                        stagione=request.form.get("stagione") or None))

        stagioni = albo_oro_repo.stagioni(cur)
        richiesta = request.args.get("stagione", "").strip()
        stagione = stagioni[0] if stagioni else ""
        if richiesta:
            try:
                stagione = dominio_albo_oro.stagione_valida(richiesta)
            except ErroreDominio as e:
                flash(e.messaggio_utente, "danger")
        vista = (dominio_albo_oro.vista_stagione(albo_oro_repo.per_stagione(cur, stagione), len(nomi))
                 if stagione else None)

    return render_template("admin_albo_oro.html", stagioni=stagioni, stagione=stagione,
                           vista=vista, squadre=squadre)


@admin_bp.route("/draft")
def admin_draft():
    """Gestione del draft U21: ordine, apertura, scelte per le squadre assenti."""
    with connessione() as (conn, cur):
        anno = request.args.get("anno", type=int)
        if anno is None:
            aperto = draft_sessione_repo.aperto(cur)
            anno = aperto["anno"] if aperto else draft_repo.primo_anno_da_giocare(cur)
        if anno is None:
            return render_template("admin_draft.html", vista=None)

        vista = servizio_draft.vista(cur, anno)
        anteprima = None
        if not vista["sessione"] or vista["sessione"]["stato"] == "preparato":
            anteprima = servizio_draft.anteprima_ordine(cur, anno)
        pool = []
        if vista["in_corso"]:
            pool = [{**g, "campioncino": url_campioncino(g["id_fantacalcio"])}
                    for g in servizio_draft.pool(cur)]

    return render_template("admin_draft.html", vista=vista, anteprima=anteprima, pool=pool)


def _azione_draft(azione, messaggio, evento=None):
    """Esegue un'azione del draft in una transazione e annuncia l'esito.

    `azione(cur, anno)` ritorna l'esito; `messaggio(esito)` e' il testo di
    successo. Il commit e' qui, e Telegram parte dopo: una richiesta annullata
    non annuncia niente.
    """
    anno = request.form.get("anno", type=int)
    if anno is None:
        flash("❌ Richiesta non valida.", "danger")
        return redirect(url_for("admin.admin_draft"))

    with connessione() as (conn, cur):
        try:
            esito = azione(cur, anno)
            conn.commit()
        except servizio_draft.SceltaNonValida as e:
            conn.rollback()
            flash(f"❌ {e}", "danger")
            return redirect(url_for("admin.admin_draft", anno=anno))
        if evento:
            annuncia_draft(cur, anno, esito, evento=evento, da_admin=True)

    flash(f"✅ {messaggio(esito)}", "success")
    return redirect(url_for("admin.admin_draft", anno=anno))


def _admin_draft_da():
    return f"admin:{session.get('username', 'admin')}"


@admin_bp.route("/draft/genera", methods=["POST"])
def admin_draft_genera():
    return _azione_draft(servizio_draft.genera_ordine,
                         lambda n: f"Ordine generato: {n} pick numerate.")


@admin_bp.route("/draft/apri", methods=["POST"])
def admin_draft_apri():
    return _azione_draft(servizio_draft.apri, lambda esito: "Draft aperto.", evento="apertura")


@admin_bp.route("/draft/scegli", methods=["POST"])
def admin_draft_scegli():
    """L'admin sceglie per la squadra on the clock (assente)."""
    id_pick = request.form.get("id_pick", type=int)
    id_giocatore = request.form.get("id_giocatore", type=int)
    return _azione_draft(
        lambda cur, anno: servizio_draft.scegli(
            cur, anno, id_pick, id_giocatore, squadra=None, e_admin=True, da=_admin_draft_da()),
        lambda esito: f"Scelto {esito['giocatore']['nome']} per {esito['pick']['detentore_att']}.",
        evento="scelta")


@admin_bp.route("/draft/salta", methods=["POST"])
def admin_draft_salta():
    id_pick = request.form.get("id_pick", type=int)
    return _azione_draft(
        lambda cur, anno: servizio_draft.salta(cur, anno, id_pick, da=_admin_draft_da()),
        lambda esito: f"Pick n. {esito['pick']['numero']} saltata.",
        evento="salto")


@admin_bp.route("/stadi", methods=["GET", "POST"])
def admin_stadi():
    """Nome e livello dello stadio di ogni squadra (crea lo stadio se manca)."""
    with connessione() as (conn, cur):
        if request.method == "POST":
            squadre_valide = set(squadre_repo.nomi(cur))
            livello_max = len(rendite_in_uso(cur)) - 1
            n_salvati = 0
            try:
                for squadra in request.form.getlist("squadra"):
                    if squadra not in squadre_valide:
                        continue
                    nome = request.form.get(f"nome_{squadra}", "")
                    livello = request.form.get(f"livello_{squadra}", "")
                    if not nome.strip() and not livello.strip():
                        continue  # squadra senza stadio e campi lasciati vuoti
                    nome, livello = dominio_albo_oro.stadio_valido(nome, livello, livello_max)
                    stadio_repo.imposta(cur, squadra, nome, livello)
                    n_salvati += 1
                conn.commit()
                flash(f"✅ Stadi salvati ({n_salvati}).", "success")
            except ErroreDominio as e:
                conn.rollback()
                flash(e.messaggio_utente, "danger")
            except psycopg2.errors.UniqueViolation:
                conn.rollback()
                flash("❌ Esiste già uno stadio con quel nome.", "danger")
            return redirect(url_for("admin.admin_stadi"))

        squadre = squadre_repo.tutte_con_stadio(cur)
        salvate = stadio_repo.rendite(cur)

    rendite = salvate or list(RENDITA_STADIO)
    accrediti = rendite_da_accreditare(squadre, rendite)
    # Gettone monouso per il pulsante di accredito: vale per questa pagina e
    # si consuma al primo invio, cosi' un doppio clic o un reinvio del form
    # non accredita due volte.
    session["token_rendite"] = secrets.token_hex(16)

    return render_template("admin_stadi.html", squadre=squadre, rendite=rendite,
                           rendite_modificabili=salvate is not None,
                           accrediti_squadre=len(accrediti),
                           accrediti_totale=sum(c for _, c in accrediti),
                           token_rendite=session["token_rendite"])


@admin_bp.route("/stadi/accredita_rendite", methods=["POST"])
def admin_accredita_rendite():
    """Accredita a ogni squadra la rendita annuale del proprio stadio.

    Usa le rendite salvate (non i valori digitati e non ancora salvati nel
    form). Somma ai crediti attuali, come una Gestione Crediti.
    """
    token = session.pop("token_rendite", None)
    if not token or not secrets.compare_digest(token, request.form.get("token", "")):
        flash("⚠️ Accredito non eseguito: la pagina era scaduta o l'operazione è già stata fatta. "
              "Controlla i crediti e ricarica prima di riprovare.", "warning")
        return redirect(url_for("admin.admin_stadi"))

    with connessione() as (conn, cur):
        accrediti = rendite_da_accreditare(squadre_repo.tutte_con_stadio(cur), rendite_in_uso(cur))
        for nome, crediti in accrediti:
            squadre_repo.aggiungi_crediti(cur, nome, crediti)
        conn.commit()

    logger.info("Rendite stadi accreditate a %s squadre (totale %s)", len(accrediti), sum(c for _, c in accrediti))
    flash(f"✅ Rendite accreditate a {len(accrediti)} squadre (totale {sum(c for _, c in accrediti)} crediti).", "success")
    return redirect(url_for("admin.admin_stadi"))


@admin_bp.route("/stadi/rendite", methods=["POST"])
def admin_rendite_stadi():
    """Rendita annuale per livello di stadio (la scala del regolamento, sezione 4).

    Cambia solo quanto la pagina Crediti, Stadi e Slot mostra come rendita:
    nessun credito viene accreditato alle squadre. Il testo del regolamento
    (letto dal chatbot) non cambia da qui.
    """
    with connessione() as (conn, cur):
        salvate = stadio_repo.rendite(cur)
        if salvate is None:
            flash("❌ Tabella delle rendite non ancora creata: lancia CronJob/stadio_livello_schema.sql.", "danger")
            return redirect(url_for("admin.admin_stadi"))
        try:
            nuove = [dominio_albo_oro.rendita_valida(request.form.get(f"rendita_{livello}"), livello)
                     for livello in range(len(salvate))]
            for livello, rendita in enumerate(nuove):
                stadio_repo.imposta_rendita(cur, livello, rendita)
            conn.commit()
            flash("✅ Rendite degli stadi salvate.", "success")
        except ErroreDominio as e:
            conn.rollback()
            flash(e.messaggio_utente, "danger")
    return redirect(url_for("admin.admin_stadi"))
