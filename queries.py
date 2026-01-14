from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor

def get_crediti_squadra(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT crediti 
                FROM squadra 
                WHERE nome = %s;
    ''', (nome_squadra,))
    crediti = cur.fetchone()["crediti"]
    cur.close()
    return crediti


def get_offerta_totale(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT SUM(ultima_offerta) AS offerta_totale
                FROM asta
                WHERE squadra_vincente = %s
                    AND stato = 'in_corso';
    ''', (nome_squadra,))
    offerta_totale = cur.fetchone()["offerta_totale"] or 0
    cur.close()
    return offerta_totale


def get_slot_giocatori(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Conteggio giocatori con contratto
    cur.execute('''
                SELECT COUNT(id) AS slot_giocatori 
                FROM giocatore 
                WHERE squadra_att = %s 
                    AND tipo_contratto IN ('Hold', 'Indeterminato');
    ''', (nome_squadra,))
    slot_giocatori = cur.fetchone()["slot_giocatori"]
    cur.close()
    return slot_giocatori



def get_slot_aste(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
                      
    cur.execute('''
                SELECT COUNT(id) AS slot_aste
                FROM asta
                WHERE %s = ANY(partecipanti)
                    AND stato <> 'conclusa';
    ''', (nome_squadra,))
    slot_aste = cur.fetchone()["slot_aste"]
    cur.close()
    return slot_aste



def get_slot_occupati(conn, nome_squadra):

    return get_slot_giocatori(conn, nome_squadra) + get_slot_aste(conn, nome_squadra)



def get_slot_prestiti_in(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    # CONTEGGIO PRESTITI IN
    cur.execute('''
                SELECT COUNT(id) AS prestiti_in_num
                FROM giocatore
                WHERE squadra_att = %s 
                    AND tipo_contratto = 'Fanta-Prestito';
    ''', (nome_squadra,))
    prestiti_in_num = cur.fetchone()["prestiti_in_num"]
    cur.close()
    
    return prestiti_in_num





def get_quotazione_attuale(conn, id_giocatore):
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT quot_att_mantra 
                FROM giocatore 
                WHERE id = %s;
    ''', (id_giocatore,))
    quotazione_attuale = cur.fetchone()["quot_att_mantra"]
    quotazione_attuale = int(quotazione_attuale)
    return quotazione_attuale