from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor
import json

user_bp = Blueprint('user', __name__, url_prefix='/user')

# Sezione squadra DOPO LOGIN
@user_bp.route("/squadraLogin")
def squadraLogin():
    nome_squadra = session.get("nome_squadra")
    return render_template("squadraLogin.html", nome_squadra=nome_squadra)


# Pagina gestione aste utente
@user_bp.route("/aste")
def user_aste():
    nome_squadra = session.get("nome_squadra")
    return render_template("user_aste.html", nome_squadra=nome_squadra)


# Creazione nuova asta
@user_bp.route("/nuova_asta", methods=["GET", "POST"])
def nuova_asta():
    conn = None
    giocatori_disponibili_per_asta = []  # ✅ inizializzata sempre

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupera i giocatori disponibili per l'asta
        cur.execute('''
            SELECT nome
            FROM giocatore AS g
            WHERE tipo_contratto <> 'Svincolato'
              AND NOT EXISTS (
                  SELECT 1 FROM asta a WHERE a.giocatore = g.id
              )
        ''')
        giocatori_disponibili_per_asta = [row["nome"] for row in cur.fetchall()]

        if request.method == "POST":
            giocatore_scelto = request.form.get("giocatore", "").strip()
            if giocatore_scelto in giocatori_disponibili_per_asta:
                cur.execute('SELECT id FROM giocatore WHERE nome = %s', (giocatore_scelto,))
                row = cur.fetchone()
                if row:
                    giocatore_id = row[0]

                    cur.execute('''
                        INSERT INTO asta (giocatore, squadra_vincente, ultima_offerta, tempo_ultima_offerta,
                                          tempo_fine_asta, tempo_fine_mostra_interesse, stato, partecipanti)
                        VALUES (%s, NULL, NULL, NULL, NULL, NOW() + INTERVAL '1 days', 'mostra_interesse', %s)
                    ''', (giocatore_id, [giocatore_scelto]))
                    conn.commit()

                    flash(f"Asta per {giocatore_scelto} creata con successo!", "success")
                    return redirect(url_for("user.user_aste"))
                else:
                    flash("Giocatore non trovato nel database.", "danger")
            else:
                flash("Giocatore non valido.", "danger")

        cur.close()

    except Exception as e:
        print("Errore nuova_asta:", e)
        flash(f"Errore nella creazione dell'asta: {e}", "danger")

    finally:
        cur.close()
        conn.close()

    return render_template("user_nuova_asta.html", giocatori_disponibili_per_asta=giocatori_disponibili_per_asta)
