import psycopg2
import telegram_utils
from datetime import datetime, time
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from db import get_connection, release_connection
from user import formatta_data
from queries import get_crediti_squadra, get_offerta_totale, get_slot_prestiti_in, sposta_crediti

prestiti_bp = Blueprint('prestiti', __name__, url_prefix='/prestiti')


@prestiti_bp.route("/prestiti/<nome_squadra>", methods=["GET", "POST"])
def user_prestiti(nome_squadra):
    conn = None
    cur = None
    crediti = 0
    crediti_disponibili = 0
    prestiti = []

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Bottone ANNULLA prestito
            id_prestito_da_annullare = request.form.get("annulla_prestito")
            if id_prestito_da_annullare:
                cur.execute('''
                            UPDATE prestito
                            SET stato = 'annullato'
                            WHERE id = %s;
                ''', (id_prestito_da_annullare,))
                conn.commit()
                flash("✅ Annullata con successo la richiesta di prestito", "success")


            # Bottone ACCETTA prestito
            id_prestito_da_accettare = request.form.get("accetta_prestito")
            if id_prestito_da_accettare:
                attiva_prestito(id_prestito_da_accettare, nome_squadra)

            
            # Bottone RIFIUTA prestito
            id_prestito_da_rifiutare = request.form.get("rifiuta_prestito")
            if id_prestito_da_rifiutare:
                cur.execute('''
                            UPDATE prestito
                            SET stato = 'rifiutato'
                            WHERE id = %s;
                ''', (id_prestito_da_rifiutare,))
                conn.commit()
                flash("✅ Prestito rifiutato con successo.", "success")
                telegram_utils.prestito_risposta(conn, id_prestito_da_rifiutare, "Rifiutato")




        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        crediti_disponibili = crediti - offerta_totale

        # Selezione dei prestiti che non sono associati con nessuno scambio
        cur.execute('''
                    SELECT *, p.id AS prestito_id, 
                           p.note,
                           p.costo_prestito,
                           p.tipo_prestito,
                           p.crediti_riscatto
                    FROM prestito p
                    JOIN giocatore g ON p.giocatore = g.id
                    WHERE (p.squadra_prestante = %s OR p.squadra_ricevente = %s)
                        AND p.stato = 'in_attesa'
                        AND NOT EXISTS (
                            SELECT 1
                            FROM scambio s
                            WHERE p.id = ANY(s.prestiti_associati)
                        );
        ''', (nome_squadra, nome_squadra))
        prestiti_raw = cur.fetchall()

        prestiti = []

        for p in prestiti_raw:
            prestiti.append({
                "prestito_id": p["prestito_id"],
                "giocatore": p["nome"],
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
        prestiti_in_num = get_slot_prestiti_in(conn, nome_squadra)
        if prestiti_in_num >= 2:
            block_button = True


    except Exception as e:
        print(f"❌ Errore durante il caricamento della pagina 'prestiti': {e}")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=0, crediti_disponibili=0, prestiti=[], prestiti_in_num=0, block_button=False)
    
    finally:
        release_connection(conn, cur)

    return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=crediti, crediti_disponibili=crediti_disponibili, prestiti=prestiti, prestiti_in_num=prestiti_in_num, block_button=block_button)





@prestiti_bp.route("/nuovo_prestito/<nome_squadra>", methods=["GET", "POST"])
def nuovo_prestito(nome_squadra):
    conn = None
    cur = None
    crediti = 0
    crediti_disponibili = 0
    giocatori = []
    squadre = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            squadra_prestante = request.form.get("squadra_prestante")
            giocatore_richiesto = request.form.get("giocatore_richiesto")
            data_fine = request.form.get("data_fine")
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
                return redirect(url_for("user.nuovo_prestito", nome_squadra=nome_squadra))
            
            data_fine = datetime.strptime(data_fine, "%Y-%m-%d")
            data_fine = datetime.combine(data_fine.date(), time(hour=23, minute=59, second=59))

            cur.execute('''
                        INSERT INTO prestito (
                        giocatore, squadra_prestante, squadra_ricevente, stato, data_inizio, data_fine, note, costo_prestito, tipo_prestito, crediti_riscatto)
                        VALUES(%s, %s, %s, %s, NOW() AT TIME ZONE 'Europe/Rome', %s, %s, %s, %s, %s)
                        RETURNING id;
            ''', (giocatore_richiesto, squadra_prestante, nome_squadra, 'in_attesa', data_fine, note, costo_prestito, tipo_prestito, crediti_riscatto))
            id_prestito = cur.fetchone()['id']
            conn.commit()
            flash("✅ Richiesta inviata correttamente!", "success")
            telegram_utils.nuovo_prestito(conn, id_prestito)
            return redirect(url_for("prestiti.user_prestiti", nome_squadra=nome_squadra))
            


        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        crediti_disponibili = crediti - offerta_totale

        # Selezione dei giocatori
        cur.execute('''
                    SELECT id, nome, squadra_att
                    FROM giocatore g
                    WHERE g.tipo_contratto <> 'Fanta-Prestito'
                    AND g.squadra_att <> 'Svincolato'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM prestito p
                        WHERE p.giocatore = g.id
                        AND p.stato = 'in_attesa'
                        AND p.squadra_ricevente = %s);
        ''', (nome_squadra,))
        giocatori_raw = cur.fetchall()

        giocatori = []
        for g in giocatori_raw:
            giocatori.append({
                "id": g["id"],
                "nome": g["nome"],
                "squadra_att": g["squadra_att"]
            })

        # Selezione dei nomi delle squadre, tranne la squadra loggata e Svincolato
        cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome <> %s
                    AND nome <> 'Svincolato';
        ''', (nome_squadra,))
        squadre_raw = cur.fetchall()

        squadre = []
        for s in squadre_raw:
            squadre.append({
                "nome": s["nome"]
            })

    except Exception as e:
        print(f"❌ Errore durante il caricamento della pagina 'nuovo_prestito': {e}")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=0, crediti_disponibili=0, prestiti=[], prestiti_in_num=0, block_button=False)
    
    finally:
        release_connection(conn, cur)

    return render_template("user_nuovo_prestito.html", nome_squadra=nome_squadra, crediti=crediti, crediti_disponibili=crediti_disponibili, giocatori=giocatori, squadre=squadre)





def attiva_prestito(id_prestito_da_attivare, nome_squadra):

    if not id_prestito_da_attivare:
        flash("❌ Prestito non trovato.", "danger")
        return redirect(url_for("prestiti.user_prestiti", nome_squadra=nome_squadra))
    
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupero info prestito
        cur.execute('''
                    SELECT *
                    FROM prestito
                    WHERE id = %s;
        ''', (id_prestito_da_attivare,))
        prestito = cur.fetchone()

        # Cambio di stato
        cur.execute('''
                    UPDATE prestito
                    SET stato = 'in_corso'
                    WHERE id = %s;
        ''', (id_prestito_da_attivare,))
        
        # Modifica info giocatore
        cur.execute('''
                    UPDATE giocatore
                    SET squadra_att = %s,
                    tipo_contratto = 'Fanta-Prestito'
                    WHERE id = %s;
        ''', (prestito['squadra_ricevente'], prestito['giocatore']))
        
        # Cancellare altri prestiti per lo stesso giocatore fatti da altre squadre
        cur.execute('''
                    UPDATE prestito
                    SET stato = 'rifiutato'
                    WHERE squadra_prestante = %s
                    AND giocatore = %s
                    AND stato = 'in_attesa';
        ''', (prestito['squadra_prestante'], prestito['giocatore']))
        
        sposta_crediti(conn, prestito['squadra_ricevente'], prestito['squadra_prestante'], prestito['costo_prestito'])

        conn.commit()
        flash("✅ Prestito avviato correttamente.", "success")
        telegram_utils.prestito_risposta(conn, id_prestito_da_attivare, "Accettato")


    except Exception as e:
        print(f"❌ Errore durante l'attivazione del prestito: {e}")
        return render_template("user_prestiti.html", nome_squadra=nome_squadra, crediti=0, crediti_disponibili=0, prestiti=[], prestiti_in_num=0, block_button=False)
    
    finally:
        release_connection(conn, cur)
