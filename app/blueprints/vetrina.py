from flask import Blueprint, render_template
from app.core.db import connessione
from app.repositories import squadre as squadre_repo
from app.repositories import vetrina as vetrina_repo

from app.core.logging import get_logger
from app.core.tempo import formatta_data
from app.domini.ruoli import pulisci_ruolo, ruoli_base_presenti

logger = get_logger(__name__)


vetrina_bp = Blueprint('vetrina', __name__, url_prefix='/vetrina')

@vetrina_bp.route('/vetrina', methods=['GET'])
def vetrina():
    giocatori = []
    squadre = []

    with connessione() as (conn, cur):
        for giocatore in vetrina_repo.elenco(cur):
            giocatori.append({
                'nome': giocatore['nome'],
                'ruolo': pulisci_ruolo(giocatore['ruolo']),
                'detentore_cartellino': giocatore['detentore_cartellino'],
                'quot_att_mantra': giocatore['quot_att_mantra'],
                'stato': giocatore['stato'],
                'note': giocatore['note'],
                'data_inserimento': formatta_data(giocatore['data_inserimento'])
        })

        squadre = squadre_repo.nomi(cur)

    ruoli_disponibili = ruoli_base_presenti([g['ruolo'] for g in giocatori])

    return render_template('vetrina.html', giocatori=giocatori, squadre=squadre, ruoli_disponibili=ruoli_disponibili)