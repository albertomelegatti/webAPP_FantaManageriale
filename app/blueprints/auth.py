"""
Autenticazione: login, logout e cambio password.

Corpo delle funzioni spostato da main.py senza modifiche di logica: cambiano
solo il decoratore e i nomi degli endpoint nelle url_for.
"""

import psycopg2
from flask import (Blueprint, flash, redirect, render_template, request,
                   session, url_for)
from psycopg2.extras import RealDictCursor
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.db import get_connection, release_connection

auth_bp = Blueprint('auth', __name__)


# Rotta per login admin
@auth_bp.route("/login", methods=["GET", "POST"])
def login():

    # Se l'utente è già loggato, viene mandato alla schermata giusta
    if session.get("logged_in"):
        if session.get("is_admin"):
            return redirect(url_for('admin.admin_home'))
        elif session.get("nome_squadra"):
            return redirect(url_for('user.squadra_login', nome_squadra=session["nome_squadra"]))
        return redirect(url_for('pubblico.home'))

    error = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if not username or not password:
            flash("❌ Compila tutti i campi.", "danger")
            return redirect(url_for('auth.login'))

        conn = None
        cur = None
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Login admin
            if username == "admin":
                cur.execute('''
                            SELECT hash_password
                            FROM admin
                            WHERE username = %s;
                ''', (username,))
                row = cur.fetchone()

                if row and check_password_hash(row["hash_password"], password):
                    session.clear()
                    session["logged_in"] = True
                    session["is_admin"] = True
                    session["username"] = username
                    session.permanent = True
                    return redirect(url_for('admin.admin_home'))

                else:
                    flash("❌ Credenziali admin errate.", "danger")

            # Login squadra
            else:
                cur.execute('''
                            SELECT hash_password, nome
                            FROM squadra
                            WHERE username = %s;
                ''', (username,))
                row = cur.fetchone()

                if row is not None:
                    hash_password = row["hash_password"]
                    nome_squadra = row["nome"]
                    if check_password_hash(hash_password, password):
                        session.clear()
                        session["logged_in"] = True
                        session["nome_squadra"] = row["nome"]
                        session["is_admin"] = False
                        session["username"] = username
                        session.permanent = True
                        return redirect(url_for('user.squadra_login', nome_squadra=nome_squadra))
                    else:
                        flash("❌ Password errata.", "danger")
                else:
                    flash("❌ Username non trovato.", "danger")

        except Exception as e:
            print("Errore login:", e)
            flash("❌ Errore di connessione al database.", "danger")

        finally:
            release_connection(conn, cur)

        return redirect(url_for('auth.login'))

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("✅ Hai effettuato il logout.", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route('/cambia_password', methods=['GET', 'POST'])
def cambia_password():

    if request.method == 'POST':
        username = session.get('username')
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if new_password != confirm_password:
            flash("❌ Le password non corrispondono.", "danger")
            return redirect(url_for('auth.cambia_password'))

        conn = None
        cur = None
        try:
            conn = get_connection()
            conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute('''
                        SELECT hash_password
                        FROM squadra
                        WHERE username = %s;
            ''', (username,))
            row = cur.fetchone()

            if row and check_password_hash(row["hash_password"], old_password):
                new_hashed_password = generate_password_hash(new_password)

                cur.execute('''
                            UPDATE squadra
                            SET hash_password = %s
                            WHERE username = %s;
                ''', (new_hashed_password, username))
                conn.commit()

                cur.execute('''
                            SELECT nome
                            FROM squadra
                            WHERE username = %s;
                ''', (username,))
                nome_squadra = cur.fetchone()["nome"]

                return redirect(url_for('user.squadra_login', nome_squadra=nome_squadra))

            flash("❌ Errore nel cambio password.", "danger")

        except Exception as e:
            print("Errore cambio password:", e)
            flash("❌ Errore durante l'aggiornamento della password.", "danger")

        finally:
            release_connection(conn, cur)

        return redirect(url_for('auth.cambia_password'))

    return render_template("change_password.html")
