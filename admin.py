import psycopg2
from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import get_connection, release_connection
from telegram_utils import send_message
from psycopg2.extras import RealDictCursor
from psycopg2 import extensions

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Rotta per area admin
@admin_bp.route("/")
def admin_home():
    return render_template("admin_home.html")

@admin_bp.route("/crediti", methods=["GET", "POST"])
def admin_crediti():
    
    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            i = 0
            while f"squadre[{i}][nome]" in request.form:
                nome = request.form.get(f"squadre[{i}][nome]")
                nuovo_credito = request.form.get(f"squadre[{i}][nuovo_credito]")
                if nome and nuovo_credito:
                    cur.execute('''
                                UPDATE squadra
                                SET crediti = %s
                                WHERE nome = %s;
                    ''',(nuovo_credito, nome))
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

    squadre = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            text_to_send = request.form.get("text_to_send")
            print(text_to_send)

            cur.execute('''
                    SELECT nome
                    FROM squadra
                    WHERE nome <> 'Svincolato';
            ''')
            squadre_raw = cur.fetchall()
            squadre = [{"nome": s["nome"]} for s in squadre_raw]

            if text_to_send:
                for s in squadre:
                    send_message(s['nome'], text_to_send)
                    print("")

                flash("✅ Messaggi inviati con successo.", "success")


    except Exception as e:
        print(f"Errore: {e}")

    finally:
        release_connection(conn, cur)

    return render_template("admin_comunicazione.html", squadre=squadre)
        


