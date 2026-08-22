from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from db import get_connection, release_connection
from user import formatta_data
from queries import get_crediti_squadra, get_offerta_totale, get_slot_prestiti_in, sposta_crediti, ruolo_base_sort_key



vetrina_bp = Blueprint('vetrina', __name__, url_prefix='/vetrina')

@vetrina_bp.route('/vetrina', methods=['GET'])
def vetrina():
    conn = None
    cur = None
    giocatori = []
    squadre = []

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute('''
            SELECT g.nome, g.ruolo, g.detentore_cartellino, g.quot_att_mantra, v.stato, v.note, v.data_inserimento
            FROM giocatore g
            JOIN vetrina v ON g.id = v.id_giocatore
            WHERE g.squadra_att <> 'Svincolato' AND g.detentore_cartellino <> 'Svincolato'
            ORDER BY g.nome;
        ''')
        giocatori_vetrina = cur.fetchall()

        for giocatore in giocatori_vetrina:
            ruolo = (giocatore['ruolo'] or '').strip("{}")
            giocatori.append({
                'nome': giocatore['nome'],
                'ruolo': ruolo,
                'detentore_cartellino': giocatore['detentore_cartellino'],
                'quot_att_mantra': giocatore['quot_att_mantra'],
                'stato': giocatore['stato'],
                'note': giocatore['note'],
                'data_inserimento': formatta_data(giocatore['data_inserimento'])
        })

        # Recupero nomi delle squadre per visualizzarli nella vetrina
        cur.execute('''
            SELECT nome
            FROM squadra
            WHERE nome <> 'Svincolato'
            ORDER BY nome;
        ''')
        squadre = cur.fetchall()

    except Exception as e:
        print(f"Errore durante il caricamento della vetrina: {e}")
        flash("❌ Errore durante il caricamento della vetrina.", "danger")

    finally:
        release_connection(conn, cur)

    ruoli_base = set()
    for g in giocatori:
        for token in (g['ruolo'] or '').split(','):
            token = token.strip()
            if token:
                ruoli_base.add(token)

    ruoli_disponibili = sorted(ruoli_base, key=ruolo_base_sort_key)

    return render_template('vetrina.html', giocatori=giocatori, squadre=squadre, ruoli_disponibili=ruoli_disponibili)