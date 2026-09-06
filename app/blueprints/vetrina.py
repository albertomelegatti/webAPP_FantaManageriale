from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.core.db import connessione
from app.queries import get_crediti_squadra, get_offerta_totale, get_slot_prestiti_in, sposta_crediti

from app.core.logging import get_logger
from app.core.tempo import formatta_data
from app.domini.ruoli import pulisci_ruolo, ruoli_base_presenti

logger = get_logger(__name__)


vetrina_bp = Blueprint('vetrina', __name__, url_prefix='/vetrina')

@vetrina_bp.route('/vetrina', methods=['GET'])
def vetrina():
    giocatori = []
    squadre = []

    try:
        with connessione() as (conn, cur):
            cur.execute('''
                SELECT g.nome, g.ruolo, g.detentore_cartellino, g.quot_att_mantra, v.stato, v.note, v.data_inserimento
                FROM giocatore g
                JOIN vetrina v ON g.id = v.id_giocatore
                WHERE g.squadra_att <> 'Svincolato' AND g.detentore_cartellino <> 'Svincolato'
                ORDER BY g.nome;
            ''')
            giocatori_vetrina = cur.fetchall()

            for giocatore in giocatori_vetrina:
                ruolo = pulisci_ruolo(giocatore['ruolo'])
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
        logger.exception("Errore durante il caricamento della vetrina")
        flash("❌ Errore durante il caricamento della vetrina.", "danger")


    ruoli_disponibili = ruoli_base_presenti([g['ruolo'] for g in giocatori])

    return render_template('vetrina.html', giocatori=giocatori, squadre=squadre, ruoli_disponibili=ruoli_disponibili)