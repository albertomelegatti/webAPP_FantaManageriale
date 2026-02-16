import psycopg2
import time
import logging
import telegram_utils
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from user import formatta_data
from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
from psycopg2 import extensions

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


class ExcludeStaticFilesFilter(logging.Filter):
    
    # Filtra i log per escludere le richieste di file CSS e JS.
    # Riduce il rumore nei log durante lo sviluppo.
    
    def filter(self, record):
        # Esclude i log per file CSS e JS
        if record.getMessage():
            msg = record.getMessage()
            if '.css' in msg or '.js' in msg or '.ico' in msg or 'favicon' in msg or '.png' in msg or '.jpg' in msg or '.jpeg' in msg:
                return False
        return True


def configure_logging():
    
    # Configura i log per escludere file CSS, JS e le immagini.
    # Chiama questa funzione in main.py dopo la creazione dell'app.
    
    # Ottieni il logger di werkzeug (Flask's built-in logger)
    log = logging.getLogger('werkzeug')
    
    # Aggiungi il filtro personalizzato
    log.addFilter(ExcludeStaticFilesFilter())
    
    print("✅ Logging configurato: file CSS, JS e immagini escluse dai log")

# Rotta per area admin
@admin_bp.route("/")
def admin_home():
    return render_template("admin_home.html")

@admin_bp.route("/crediti", methods=["GET", "POST"])
def admin_crediti():
    conn = None
    cur = None
    squadre = []
    
    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            i = 0
            max_squadre = 100  # Protezione contro loop infinito
            while f"squadre[{i}][nome]" in request.form and i < max_squadre:
                nome = request.form.get(f"squadre[{i}][nome]")
                nuovo_credito = request.form.get(f"squadre[{i}][nuovo_credito]")
                if nome and nuovo_credito:
                    try:
                        nuovo_credito = int(nuovo_credito)
                        cur.execute('''
                                    UPDATE squadra
                                    SET crediti = %s
                                    WHERE nome = %s;
                        ''', (nuovo_credito, nome))
                    except ValueError:
                        print(f"Valore crediti non valido per squadra {nome}")
                i += 1
            conn.commit()
            flash("✅ Tutti i crediti sono stati aggiornati con successo!", "success")
            return redirect(url_for("admin.admin_crediti"))


        cur.execute('''
                    SELECT nome, crediti
                    FROM squadra
                    WHERE nome <> 'Svincolato'
                    ORDER BY nome ASC;''')
        squadre_raw = cur.fetchall()
        squadre = [{"nome": s["nome"], "crediti": s["crediti"]} for s in squadre_raw]

    except Exception as e:
        print("Errore", e)
        flash("❌ Errore durante il caricamento o l'aggiornamento dei crediti.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("admin_crediti.html", squadre=squadre)




@admin_bp.route("/invia_comunicazione", methods=["GET", "POST"])
def invia_comunicazione():
    conn = None
    cur = None
    squadre = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            text_to_send = request.form.get("text_to_send", "").strip()
            
            if not text_to_send:
                flash("❌ Il messaggio non può essere vuoto.", "warning")
                return redirect(url_for("admin.invia_comunicazione"))
            telegram_utils.send_message(nome_squadra='gruppo_comunicazioni', text_to_send=text_to_send)
            
            flash(f"✅ Messaggi inviati a {len(squadre)} squadre.", "success")


    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(conn, cur)

    return render_template("admin_comunicazione.html", squadre=squadre)



@admin_bp.route("/richiesta/modifica/contratto", methods=["GET", "POST"])
def richiesta_modifica_contratto():
    conn = None
    cur = None
    richieste = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # RIFIUTA RICHIESTA DI MODIFICA CONTRATTO
            if request.form.get("rifiuta_richiesta"):
                id_richiesta = request.form.get("id_richiesta")

                # Aggiornamento stato richiesta
                cur.execute('''
                            UPDATE richiesta_modifica_contratto
                            SET stato = 'rifiutata'
                            WHERE id = %s;
                ''', (id_richiesta,))
                conn.commit()
                flash("✅ Richiesta di modifica contratto rifiutata con successo.", "success")
                telegram_utils.richiesta_modifica_contratto_risposta(conn, id_richiesta, "Rifiutato")



            # ACCETTA RICHIESTA DI MODIFICA CONTRATTO
            if request.form.get("accetta_richiesta"):
                id_richiesta = request.form.get("id_richiesta")

                # Aggiornamento stato richiesta
                cur.execute('''
                            UPDATE richiesta_modifica_contratto
                            SET stato = 'accettata'
                            WHERE id = %s;
                ''', (id_richiesta,))

                # Recupero informazioni sulla richiesta
                cur.execute('''
                            SELECT giocatore, contratto_richiesto, crediti_richiesti, squadra_richiedente
                            FROM richiesta_modifica_contratto
                            WHERE id = %s;
                ''', (id_richiesta,))
                row = cur.fetchone()
                id_giocatore = row['giocatore']
                nuovo_contratto = row['contratto_richiesto']
                crediti_richiesti = row['crediti_richiesti']
                squadra_richiedente = row['squadra_richiedente']

                # Logica per aggiornare squadra_attuale e detentore_cartellino
                if nuovo_contratto == 'Svincolato':
                    # Se il contratto è "Svincolato", 
                    # squadra attuale e detentore cartellino vanno a "Svincolato"
                    cur.execute('''
                                UPDATE giocatore
                                SET tipo_contratto = %s,
                                    squadra_att = %s,
                                    detentore_cartellino = %s
                                WHERE id = %s;
                    ''', (nuovo_contratto, 'Svincolato', 'Svincolato', id_giocatore))
                elif nuovo_contratto == 'Prestito Reale':
                    # Se il contratto è "Prestito Reale", 
                    # squadra attuale va a "Svincolato"
                    cur.execute('''
                                UPDATE giocatore
                                SET tipo_contratto = %s,
                                    squadra_att = %s
                                WHERE id = %s;
                    ''', (nuovo_contratto, 'Svincolato', id_giocatore))
                elif nuovo_contratto == 'Indeterminato':
                    # Se il contratto è "Indeterminato", 
                    # squadra attuale va a tonra a  detentore cartellino
                    cur.execute('''
                                UPDATE giocatore
                                SET tipo_contratto = %s,
                                    squadra_att = %s
                                WHERE id = %s;
                    ''', (nuovo_contratto, squadra_richiedente, id_giocatore))
                else:
                    # Per altri tipi di contratto, aggiorna solo il tipo di contratto
                    cur.execute('''
                                UPDATE giocatore
                                SET tipo_contratto = %s
                                WHERE id = %s;
                    ''', (nuovo_contratto, id_giocatore))

                # Aggiornamento crediti squadra: la modifica contratto assegna i crediti richiesti
                cur.execute('''
                            UPDATE squadra
                            SET crediti = crediti + %s
                            WHERE nome = %s;
                ''', (crediti_richiesti, squadra_richiedente))


                conn.commit()
                flash("✅ Richiesta di modifica contratto accettata con successo.", "success")
                telegram_utils.richiesta_modifica_contratto_risposta(conn, id_richiesta, "Accettato")
                return redirect(url_for("admin.richiesta_modifica_contratto"))








        cur.execute('''
                    SELECT r.id, g.nome, g.tipo_contratto, r.giocatore, r.contratto_richiesto, r.squadra_richiedente, r.crediti_richiesti, r.messaggio, r.data, r.stato
                    FROM richiesta_modifica_contratto AS r
                    JOIN giocatore AS g
                    ON r.giocatore = g.id
                    ORDER BY data DESC;
        ''')
        richieste_raw = cur.fetchall()
        richieste = []

        for r in richieste_raw:
            richieste.append({
                "id": r["id"],
                "nome_giocatore": r["nome"],
                "contratto_attuale": r["tipo_contratto"],
                "contratto_richiesto": r["contratto_richiesto"],
                "squadra_richiedente": r["squadra_richiedente"],
                "crediti_richiesti": r["crediti_richiesti"],
                "messaggio": r["messaggio"],
                "data": formatta_data(r["data"]),
                "stato": r["stato"]
            })

    except Exception as e:
        print("Errore:", e)
        flash("❌ Errore durante il caricamento delle richieste.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("admin_richiesta_modifica_contratto.html", richieste=richieste)