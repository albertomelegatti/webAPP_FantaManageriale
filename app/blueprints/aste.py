import psycopg2
import os
from app import telegram_utils
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.core.db import connessione, resync_sequence
from app.blueprints.user import format_partecipanti, redirect_gate_chiuso
from dotenv import load_dotenv

from app.core.logging import get_logger
from app.core.tempo import formatta_data
from app.domini.ruoli import pulisci_ruolo
from app.repositories import aste as aste_repo
from app.repositories import giocatori as giocatori_repo
from app.repositories import configurazione as configurazione_repo
from app.repositories import squadre as squadre_repo

logger = get_logger(__name__)

load_dotenv()


aste_bp = Blueprint('aste', __name__, url_prefix='/aste')


@aste_bp.before_request
def blocca_aste_chiuse():
    with connessione() as (conn, cur):
        if not configurazione_repo.aste_aperte(cur):
            flash("❌ Le aste sono chiuse.", "danger")
            return redirect_gate_chiuso()


# Pagina gestione aste utente
@aste_bp.route("/aste/<nome_squadra>", methods=["GET", "POST"])
def user_aste(nome_squadra):
    try:
        with connessione(isolamento=psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ) as (conn, cur):
            if request.method == "POST":

                # BOTTONE ISCRIVITI
                asta_id = request.form.get("asta_id_aste_a_cui_iscriversi")
                if asta_id:

                    # Controllo che l'asta non sia scaduta nel mentre che la pagina era aperta
                    tempo_scaduto = False
                    stato = aste_repo.stato(cur, asta_id)

                    if stato != 'mostra_interesse':
                        tempo_scaduto = True
                        flash("❌ Iscrizione fallita, tempo scaduto.", "danger")
                        return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))

                
                    if tempo_scaduto == False:
                        # Controllo se l'utente loggato è già iscritto all'asta, a volte capita che un utente possa iscriversi due volte.
                        gia_iscritto = aste_repo.e_iscritta(cur, asta_id, nome_squadra)
                
                        # Se non gia iscritto, iscriviti
                        if not gia_iscritto:
                            aste_repo.iscrivi(cur, asta_id, nome_squadra)
                            conn.commit()

                            # Recupero info id giocatore dell'asta
                            id_giocatore = aste_repo.giocatore_dell_asta(cur, asta_id)
                            nome_giocatore = giocatori_repo.nome(cur, id_giocatore)

                            flash(f"✅ Ti sei iscritto all'asta per { nome_giocatore }.", "success")
                            return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))
            

            
            # Lista aste, tutte insieme
            aste = []
            aste_raw = aste_repo.visibili_alla_squadra(cur, nome_squadra)

            for a in aste_raw:

                data_scadenza = formatta_data(a["tempo_fine_asta"])
                tempo_fine_mostra_interesse = formatta_data(a["tempo_fine_mostra_interesse"])

                gia_iscritto_all_asta = False
                if nome_squadra in a["partecipanti"]:
                    gia_iscritto_all_asta = True

                partecipanti = format_partecipanti(a["partecipanti"])

                aste.append({
                    "asta_id": a["id"],
                    "giocatore": a["nome"],
                    "ruolo": pulisci_ruolo(a["ruolo"]),
                    "club": a["club"],
                    "squadra_vincente": a["squadra_vincente"],
                    "ultima_offerta": a["ultima_offerta"],
                    "tempo_fine_mostra_interesse": tempo_fine_mostra_interesse,
                    "data_scadenza": data_scadenza,
                    "stato": a["stato"],
                    "partecipanti": partecipanti,
                    "gia_iscritto_all_asta": gia_iscritto_all_asta
                })

        

            # Ottengo i crediti e i crediti disponibili
            crediti, offerta_totale = squadre_repo.crediti_e_offerta(cur, nome_squadra)
            offerta_massima_possibile = crediti - offerta_totale
            slot_occupati = aste_repo.slot_occupati_totali(cur, nome_squadra)

            block_button = False
            if crediti == 0 or offerta_massima_possibile == 0 or slot_occupati >= 30:
                block_button = True

    except Exception:
        logger.exception("Errore")
        flash("❌ Errore durante il caricamento delle aste.", "danger")
        return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))


    return render_template("user_aste.html", nome_squadra=nome_squadra, aste=aste, block_button=block_button, crediti=crediti, crediti_effettivi=offerta_massima_possibile, slot_occupati=slot_occupati)


# Creazione nuova asta
@aste_bp.route("/nuova_asta/<nome_squadra>", methods=["GET", "POST"])
def nuova_asta(nome_squadra):
    giocatori_disponibili_per_asta = []
    giocatori_info_per_asta = []

    with connessione(isolamento=psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE) as (conn, cur):
        # Recupera i giocatori disponibili per l'asta, esclusi gli U21 (chiamabili
        # solo tramite draft): sono considerati U21 i giocatori nati nell'anno
        # u21_threshold_year o dopo. Se la soglia non è impostata, se il giocatore
        # non ha una data di nascita sincronizzata, o se è un portiere, nessun
        # filtro viene applicato (i portieri sono sempre chiamabili in asta).
        u21_threshold_year = configurazione_repo.soglia_u21(cur)
        giocatori_raw = giocatori_repo.chiamabili_in_asta(cur, u21_threshold_year)
        giocatori_disponibili_per_asta = [row["nome"] for row in giocatori_raw]
        giocatori_info_per_asta = [
            {"nome": row["nome"], "ruolo": pulisci_ruolo(row["ruolo"]), "club": row["club"]}
            for row in giocatori_raw
        ]


        if request.method == "POST":
            # Aggiunta nuovo giocatore
            enable_player_creation = os.getenv("ENABLE_PLAYER_CREATION", "false").lower() == "true"
            crea_nuovo = request.form.get("crea_nuovo")
        
            if crea_nuovo:
                # Verifica che la funzionalità sia abilitata
                if not enable_player_creation:
                    flash("❌ La creazione di nuovi giocatori è attualmente disabilitata.", "danger")
                    return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))
            
                # Recupera e formatta i dati del form
                nome_nuovo = request.form.get("nome_nuovo", "").strip()
                club_nuovo = request.form.get("club_nuovo", "").strip()
            
                # Formatta nomi: prima lettera di ogni parola in maiuscolo
                # Esempi: "lucca" -> "Lucca", "de bruyne" -> "De Bruyne"
                nome_nuovo = nome_nuovo.title()
                club_nuovo = club_nuovo.title() if club_nuovo else ""
            
                # Validazione: nome obbligatorio
                if not nome_nuovo:
                    flash("❌ Il nome del giocatore è obbligatorio.", "danger")
                    return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))
            
                # Verifica che il giocatore non esista già nel database
                if giocatori_repo.esiste_con_nome(cur, nome_nuovo):
                    flash("❌ Un giocatore con questo nome esiste già.", "danger")
                    return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))
            
                # Crea il nuovo giocatore nel database
                # - Ruolo: PlaceHolderRole (sarà aggiornato successivamente)
                # - Quotazione: 666 (default)
                # - Tipo contratto: Svincolato
                sql_giocatore = '''
                    INSERT INTO giocatore (
                        nome, ruolo, tipo_contratto, squadra_att, detentore_cartellino,
                        quot_att_mantra, costo, priorita, club
                    )
                    VALUES (%s, ARRAY['PlaceHolderRole']::ruolo_mantra[], 'Svincolato', 'Svincolato', 'Svincolato', 666, 0, 1, %s)
                    RETURNING id;
                '''
                giocatore_params = (nome_nuovo, club_nuovo or "N/A")

                # Crea automaticamente l'asta per il giocatore appena creato
                # - Stato: mostra_interesse
                # - Durata: 1 giorno
                # - Partecipante iniziale: squadra corrente
                sql_asta = '''
                    INSERT INTO asta (
                        giocatore, squadra_vincente, ultima_offerta,
                        tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti, gia_elaborata
                    )
                    VALUES (%s, %s, NULL, NULL, (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day', 'mostra_interesse', %s, FALSE)
                    RETURNING id;
                '''

                try:
                    cur.execute(sql_giocatore, giocatore_params)
                    nuovo_giocatore_id = cur.fetchone()["id"]
                    cur.execute(sql_asta, (nuovo_giocatore_id, nome_squadra, [nome_squadra]))
                    asta_id = cur.fetchone()["id"]
                except psycopg2.errors.UniqueViolation:
                    # La sequence di giocatore o asta è rimasta indietro rispetto ai dati
                    # (es. import/restore manuale sul DB). Il rollback annulla anche
                    # l'eventuale insert di giocatore già fatto in questo tentativo, quindi
                    # riallineiamo entrambe le sequence e rifacciamo l'intero blocco da capo,
                    # così l'utente non vede l'errore.
                    conn.rollback()
                    resync_sequence(conn, 'giocatore')
                    resync_sequence(conn, 'asta')
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute(sql_giocatore, giocatore_params)
                    nuovo_giocatore_id = cur.fetchone()["id"]
                    cur.execute(sql_asta, (nuovo_giocatore_id, nome_squadra, [nome_squadra]))
                    asta_id = cur.fetchone()["id"]

                conn.commit()
                flash(f"✅ Giocatore {nome_nuovo} creato e asta avviata con successo!", "success")
                telegram_utils.nuova_asta(conn, asta_id)
                return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))
        
            # Asta per giocatore già presente nel database
            giocatore_scelto = request.form.get("giocatore", "").strip()
            if giocatore_scelto and giocatore_scelto not in giocatori_disponibili_per_asta:
                flash("❌ Giocatore non valido o già in un'asta.", "danger")
                return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))

            # Gestione asta per giocatore esistente - continua solo se c'è un giocatore selezionato
            if giocatore_scelto:
                try:
                    # Locka il giocatore per evitare race condition
                    giocatore_id = giocatori_repo.id_per_nome_bloccando(cur, giocatore_scelto)

                    if not giocatore_id:
                        flash("❌ Giocatore non trovato nel database.", "danger")
                        return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))

                    # Inserisci l'asta
                    sql_asta = '''
                        INSERT INTO asta (
                            giocatore, squadra_vincente, ultima_offerta,
                            tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti, gia_elaborata
                        )
                        VALUES (%s, %s, NULL, NULL, (NOW() AT TIME ZONE 'Europe/Rome') + INTERVAL '1 day', 'mostra_interesse', %s, FALSE)
                        RETURNING id;
                    '''
                    asta_params = (giocatore_id, nome_squadra, [nome_squadra])
                    try:
                        cur.execute(sql_asta, asta_params)
                    except psycopg2.errors.UniqueViolation:
                        # La sequence di asta è rimasta indietro rispetto ai dati
                        # (es. import/restore manuale sul DB). Riallineiamo e riproviamo,
                        # così l'utente non vede l'errore.
                        conn.rollback()
                        resync_sequence(conn, 'asta')
                        cur = conn.cursor(cursor_factory=RealDictCursor)
                        cur.execute(sql_asta, asta_params)
                    asta_id = cur.fetchone()["id"]
                    conn.commit()

                    flash(f"✅ Asta per {giocatore_scelto} creata con successo!", "success")
                    telegram_utils.nuova_asta(conn, asta_id)
                    return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))

                except psycopg2.errors.SerializationFailure:
                    conn.rollback()
                    flash("Un altro utente ha appena creato un'asta per questo giocatore. Riprova.", "warning")
                    return redirect(url_for("aste.nuova_asta", nome_squadra=nome_squadra))

    # Controlla se la creazione di giocatori è abilitata per il template
    enable_player_creation = os.getenv("ENABLE_PLAYER_CREATION", "false").lower() == "true"

    return render_template("user_nuova_asta.html",
                         nome_squadra=nome_squadra,
                         giocatori_disponibili_per_asta=giocatori_disponibili_per_asta,
                         giocatori_info_per_asta=giocatori_info_per_asta,
                         enable_player_creation=enable_player_creation)


@aste_bp.route("/singola_asta_attiva/<int:asta_id>/<nome_squadra>", methods=["GET", "POST"])
def singola_asta_attiva(asta_id, nome_squadra):
    asta = None
    with connessione(isolamento=psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE) as (conn, cur):
        if request.method == "POST":

            # Bottone RINUNCIA
            asta_id_rinuncia = request.form.get("bottone_rinuncia")
            if asta_id_rinuncia:
                aste_repo.rinuncia(cur, asta_id_rinuncia, nome_squadra)
                conn.commit()
                flash("✅ Hai rinunciato all'asta.", "success")
                return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))

            # Bottone RILANCIA OFFERTA
            nuova_offerta = request.form.get("bottone_rilancia")
            if nuova_offerta:
                # Blocca la riga dell'asta per aggiornamenti concorrenti
                asta_dati = aste_repo.dati_per_rilancio(cur, asta_id)

                # Controllo sullo stato dell'asta prima del rilancio
                if asta_dati['stato'] != 'in_corso':
                    flash("Tempo scaduto, asta terminata.", "danger")
                    return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))


                # Controllo sui valori dell'asta prima di rilanciare
                if asta_dati['ultima_offerta'] < int(nuova_offerta) and asta_dati['squadra_vincente']:

                    aste_repo.registra_rilancio(cur, asta_id, nuova_offerta, nome_squadra)
                    conn.commit()
                    flash(f"✅ Hai rilanciato l'offerta a {nuova_offerta}.", "success")
                    telegram_utils.asta_rilanciata(conn, asta_id)
                    return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))
            
                flash("❌ Attenzione, valori non aggiornati, verrai reindirizzato alla pagina aggiornata.", "danger")
                return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))

            # Bottoni RILANCIO RAPIDO (+1 / +2 / +5)
            delta_rilancio = request.form.get("delta_rilancio")
            if delta_rilancio in ("1", "2", "5"):
                # Blocca la riga dell'asta per aggiornamenti concorrenti
                asta_dati = aste_repo.dati_per_rilancio(cur, asta_id)

                # Controllo sullo stato dell'asta prima del rilancio
                if asta_dati['stato'] != 'in_corso':
                    flash("Tempo scaduto, asta terminata.", "danger")
                    return redirect(url_for("aste.user_aste", nome_squadra=nome_squadra))

                # L'offerta vista dall'utente al caricamento della pagina: se nel
                # frattempo qualcun altro ha rilanciato, l'offerta reale in DB non
                # corrisponde più e il rilancio rapido va rifiutato invece di sommare
                # il delta a un valore ormai superato.
                offerta_attesa = request.form.get("offerta_attesa", type=int)

                if offerta_attesa is None or asta_dati['ultima_offerta'] != offerta_attesa:
                    flash(f"⚠️ Nel frattempo l'offerta è cambiata: ora è a {asta_dati['ultima_offerta']} cr "
                          f"(in testa {asta_dati['squadra_vincente']}). Ripremi +1, +2 o +5 se vuoi rilanciare "
                          f"sull'offerta aggiornata.", "warning")
                    return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))

                if not asta_dati['squadra_vincente']:
                    flash("❌ Rilancio non valido.", "danger")
                    return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))

                nuova_offerta = asta_dati['ultima_offerta'] + int(delta_rilancio)

                aste_repo.registra_rilancio(cur, asta_id, nuova_offerta, nome_squadra)
                conn.commit()
                flash(f"✅ Hai rilanciato l'offerta a {nuova_offerta}.", "success")
                telegram_utils.asta_rilanciata(conn, asta_id)
                return redirect(url_for("aste.singola_asta_attiva", asta_id=asta_id, nome_squadra=nome_squadra))


        # Recupero dati asta (join diretto sull'id dell'asta: un'unica riga,
        # non serve filtrare tutta la tabella giocatore per tipo_contratto)
        asta_raw = aste_repo.dettaglio(cur, asta_id)

        if asta_raw:
            # Recupero crediti disponibili
            crediti, offerta_totale = squadre_repo.crediti_e_offerta(cur, nome_squadra)


            # Calcolo offerta massima possibile
            if asta_raw["squadra_vincente"] == nome_squadra:
                offerta_massima_possibile = crediti - (offerta_totale - (asta_raw["ultima_offerta"] or 0))
            else:
                offerta_massima_possibile = crediti - offerta_totale

            partecipanti = format_partecipanti(asta_raw["partecipanti"])
            # Un'asta ancora in "mostra interesse" non ha una data di fine: la
            # riceve solo quando parte. Prima questo caso mandava la pagina in
            # errore, nascosto da un except che rendeva comunque il template.
            data_scadenza_str = formatta_data(asta_raw["tempo_fine_asta"]) or "—"

            asta = {
                "id": asta_id,
                "giocatore": asta_raw["nome"],
                "ruolo": pulisci_ruolo(asta_raw["ruolo"]),
                "club": asta_raw["club"],
                # Un'asta non ancora avviata non ha offerte: il template la usa
                # in operazioni aritmetiche, e None le faceva fallire.
                "ultima_offerta": asta_raw["ultima_offerta"] or 0,
                "squadra_vincente": asta_raw["squadra_vincente"],
                "tempo_fine_asta": data_scadenza_str,
                "partecipanti": partecipanti,
                "offerta_massima_possibile": offerta_massima_possibile
            }
        else:
            flash("Asta non trovata.", "warning")
            return redirect(url_for("aste.singola_asta_attiva", nome_squadra=nome_squadra))

    return render_template("singola_asta_attiva.html", asta=asta, nome_squadra=nome_squadra)

