from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

# Rotta per area admin
@admin_bp.route("/")
def admin_home():
    return render_template("admin_home.html")

@admin_bp.route("/crediti", methods=["GET", "POST"])
def admin_crediti():
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # --- POST (Salva singolo o Salva tutto) ---
        if request.method == "POST":
            # Se viene dal "Salva tutto", i campi sono in formato squadre[0][nome], etc.
            if "squadre[0][nome]" in request.form:
                i = 0
                while f"squadre[{i}][nome]" in request.form:
                    nome = request.form.get(f"squadre[{i}][nome]")
                    nuovo_credito = request.form.get(f"squadre[{i}][nuovo_credito]")
                    if nome and nuovo_credito:
                        cur.execute(
                            '''UPDATE squadra
                               SET crediti = %s
                               WHERE nome = %s;''',
                            (nuovo_credito, nome)
                        )
                    i += 1
                conn.commit()
                flash("Tutti i crediti sono stati aggiornati con successo!", "success")
                return redirect(url_for("admin.admin_crediti"))

            # Altrimenti viene da un singolo form
            nome_squadra = request.form.get("nome_squadra")
            nuovo_credito = request.form.get("nuovo_credito")
            if nome_squadra and nuovo_credito:
                cur.execute(
                    '''UPDATE squadra 
                       SET crediti = %s 
                       WHERE nome = %s;''',
                    (nuovo_credito, nome_squadra)
                )
                conn.commit()
                flash(f"Crediti della squadra {nome_squadra} aggiornati con successo!", "success")
                return redirect(url_for("admin.admin_crediti"))

        # --- GET (Popolamento tabella) ---
        cur.execute('''
            SELECT nome, crediti
            FROM squadra
            WHERE nome <> 'Svincolato'
            ORDER BY nome ASC;
        ''')
        squadre_raw = cur.fetchall()
        squadre = [{"nome": s["nome"], "crediti": s["crediti"]} for s in squadre_raw]

    except Exception as e:
        print("Errore", e)
        flash("Errore durante il caricamento o l'aggiornamento dei crediti.", "danger")

    finally:
        if conn:
            release_connection(conn)

    return render_template("admin_crediti.html", squadre=squadre)
