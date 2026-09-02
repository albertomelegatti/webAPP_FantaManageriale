import json
import psycopg2
import time
import telegram_utils
from datetime import datetime
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from user import formatta_data
from db import get_connection, release_connection
from queries import decadi_vetrina, get_stato_gate
from transfermarkt_matching import candidati_fuzzy
from psycopg2.extras import RealDictCursor
from psycopg2 import extensions

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

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




@admin_bp.route("/chiusura_mercato_aste", methods=["GET", "POST"])
def admin_chiusura_mercato_aste():
    conn = None
    cur = None
    stato_gate = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            mercato_chiusura_raw = request.form.get("mercato_chiusura") or None
            aste_chiusura_raw = request.form.get("aste_chiusura") or None

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

            cur.execute('''
                        UPDATE general_config
                        SET mercato_chiusura = %s,
                            aste_chiusura = %s
                        WHERE id = 1;
            ''', (mercato_chiusura, aste_chiusura))
            conn.commit()
            flash("✅ Impostazioni di chiusura aggiornate con successo.", "success")
            return redirect(url_for("admin.admin_chiusura_mercato_aste"))

        stato_gate = get_stato_gate(conn)

    except Exception as e:
        print("Errore:", e)
        flash("❌ Errore durante il caricamento o l'aggiornamento delle impostazioni.", "danger")

    finally:
        release_connection(conn, cur)

    return render_template("admin_chiusura_mercato_aste.html", stato_gate=stato_gate)


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
                    decadi_vetrina(cur, id_giocatore)
                elif nuovo_contratto == 'Prestito Reale':
                    # Se il contratto è "Prestito Reale",
                    # squadra attuale va a "Svincolato"
                    cur.execute('''
                                UPDATE giocatore
                                SET tipo_contratto = %s,
                                    squadra_att = %s
                                WHERE id = %s;
                    ''', (nuovo_contratto, 'Svincolato', id_giocatore))
                    decadi_vetrina(cur, id_giocatore)
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
                # "Indeterminato" e "Hold" non fanno decadere la vetrina: il giocatore
                # resta alla squadra richiedente, non è un vero movimento di mercato.

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
                    SELECT r.id, g.nome, g.tipo_contratto, g.ruolo, g.club, r.giocatore, r.contratto_richiesto, r.squadra_richiedente, r.crediti_richiesti, r.messaggio, r.data, r.stato
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
                "ruolo": (r["ruolo"] or "").strip("{}"),
                "club": r["club"],
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


@admin_bp.route("/verifica_corrispondenze_giocatori", methods=["GET", "POST"])
def admin_verifica_corrispondenze():
    conn = None
    cur = None
    giocatori_da_rivedere = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            corrispondenze_data_raw = request.form.get("corrispondenze_data", "")

            try:
                risoluzioni = json.loads(corrispondenze_data_raw) if corrispondenze_data_raw else []
            except (ValueError, TypeError):
                flash("❌ Dati inviati non validi, ricarica la pagina e riprova.", "danger")
                return redirect(url_for("admin.admin_verifica_corrispondenze"))

            cur.execute("SELECT DISTINCT id_giocatore FROM transfermarkt_giocatori WHERE id_giocatore IS NOT NULL;")
            id_giocatori_in_coda = {r["id_giocatore"] for r in cur.fetchall()}

            def rimuovi_dalla_coda(id_giocatore):
                # La riga sintetica "non trovato" (id_transfermarkt NULL) non serve più
                # a nulla una volta risolto il caso; le righe di candidati reali restano
                # come cache, tornano solo a non essere più marcate per questo giocatore.
                cur.execute(
                    "DELETE FROM transfermarkt_giocatori WHERE id_giocatore = %s AND id_transfermarkt IS NULL;",
                    (id_giocatore,),
                )
                cur.execute(
                    "UPDATE transfermarkt_giocatori SET id_giocatore = NULL WHERE id_giocatore = %s;",
                    (id_giocatore,),
                )

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
                        cur.execute(
                            '''
                            SELECT id_transfermarkt, data_nascita, scadenza_contratto
                            FROM transfermarkt_giocatori
                            WHERE id_transfermarkt = %s;
                            ''',
                            (id_tm_fuzzy_raw,),
                        )
                        row = cur.fetchone()
                        if row:
                            candidato = {
                                "id_transfermarkt": row["id_transfermarkt"],
                                "data_nascita": row["data_nascita"],
                                "scadenza_contratto": row["scadenza_contratto"],
                            }

                elif valore_scelto.isdigit():
                    cur.execute(
                        '''
                        SELECT id_transfermarkt, data_nascita, scadenza_contratto
                        FROM transfermarkt_giocatori
                        WHERE id_giocatore = %s AND id_transfermarkt = %s;
                        ''',
                        (id_giocatore, valore_scelto),
                    )
                    candidato = cur.fetchone()

                if not candidato:
                    # La selezione non è (più) valida, es. la cache è stata rigenerata da
                    # un nuovo run dello script mentre la pagina era aperta: non tocchiamo
                    # la coda, resta lì per essere rivista con dati aggiornati.
                    n_selezioni_non_valide += 1
                    continue

                cur.execute(
                    '''
                    UPDATE giocatore
                    SET id_transfermarkt = %s,
                        data_nascita = %s,
                        scadenza_contratto = %s
                    WHERE id = %s;
                    ''',
                    (candidato["id_transfermarkt"], candidato["data_nascita"],
                     candidato["scadenza_contratto"], id_giocatore),
                )
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

        cur.execute('''
                    SELECT
                        c.id_giocatore,
                        g.nome,
                        g.club,
                        g.ruolo,
                        c.id_transfermarkt,
                        c.nome AS nome_tm,
                        c.cognome AS cognome_tm,
                        c.club_tm,
                        c.data_nascita,
                        c.scadenza_contratto
                    FROM transfermarkt_giocatori c
                    JOIN giocatore g ON g.id = c.id_giocatore
                    WHERE c.id_giocatore IS NOT NULL
                    ORDER BY g.nome, c.cognome;
        ''')
        righe = cur.fetchall()

        per_giocatore = {}
        for r in righe:
            entry = per_giocatore.setdefault(r["id_giocatore"], {
                "id": r["id_giocatore"],
                "nome": r["nome"],
                "club": r["club"],
                "ruolo": (r["ruolo"] or "").strip("{}"),
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
            cur.execute("SELECT club, nome_transfermarkt FROM transfermarkt_mappa_club;")
            mappa_club = {r["club"]: r["nome_transfermarkt"] for r in cur.fetchall()}

            for g in non_trovati:
                club_tm = mappa_club.get(g["club"])
                if not club_tm:
                    continue
                cur.execute(
                    '''
                    SELECT id_transfermarkt, nome, cognome, data_nascita, scadenza_contratto
                    FROM transfermarkt_giocatori
                    WHERE club_tm = %s;
                    ''',
                    (club_tm,),
                )
                rosa_tm = cur.fetchall()
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

    except Exception as e:
        print("Errore:", e)
        flash("❌ Errore durante il caricamento delle corrispondenze da rivedere.", "danger")
        conteggi = {"ambiguo": 0, "suggerito": 0, "non_trovato": 0}

    finally:
        release_connection(conn, cur)

    return render_template("admin_verifica_corrispondenze.html", giocatori=giocatori_da_rivedere, conteggi=conteggi)