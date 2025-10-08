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

        if request.method == "POST":
            nome_squadra = request.form.get("nome_squadra")
            nuovo_credito = request.form.get("nuovo_credito")

            if nome_squadra and nuovo_credito:
                cur.execute('''UPDATE squadra 
                            SET crediti = %s 
                            WHERE nome = %s;''', (nuovo_credito, nome_squadra))
                conn.commit()
                flash("Crediti aggiornati con successo!", "success")
                return redirect(url_for("admin.admin_crediti"))


        # Popolamento della tabella
        squadre = []
        cur.execute('''SELECT nome, crediti
                    FROM squadra
                    WHERE nome <> 'Svincolato'
                    ORDER BY nome ASC;''')
        squadre_raw =cur.fetchall()

        for s in squadre_raw:
            squadre.append({
                "nome": s["nome"],
                "crediti": s["crediti"]
            })
    
    except Exception as e:
        print("Errore", e)
        flash("Errore durante il caricamento della tabella crediti.", "danger")
    
    finally:
        if conn:
            release_connection(conn)

    return render_template("admin_crediti.html", squadre=squadre)

