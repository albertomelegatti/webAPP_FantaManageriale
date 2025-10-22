from db import get_connection, release_connection
from psycopg2.extras import RealDictCursor

def get_crediti_squadra(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''SELECT crediti 
                FROM squadra 
                WHERE nome = %s;''', (nome_squadra,))
    crediti = cur.fetchone()["crediti"]
    cur.close()
    return crediti


def get_offerta_totale(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''SELECT SUM(ultima_offerta) AS offerta_totale
                    FROM asta
                    WHERE squadra_vincente = %s
                    AND stato = 'in_corso';''', (nome_squadra,))
    offerta_totale = cur.fetchone()["offerta_totale"] or 0
    cur.close()
    return offerta_totale


def get_slot_occupati(conn, nome_squadra):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''SELECT COUNT(id) AS slot_occupati 
                    FROM giocatore 
                    WHERE squadra_att = %s 
                        AND tipo_contratto IN ('Hold', 'Indeterminato');''', (nome_squadra,))
    slot_occupati = cur.fetchone()["slot_occupati"]
    cur.close()
    return slot_occupati


def get_quotazione_attuale(conn, id_giocatore):
    
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT quot_att_mantra FROM giocatore WHERE id = %s;", (id_giocatore,))
    quotazione_attuale = cur.fetchone()["quot_att_mantra"]
    quotazione_attuale = int(quotazione_attuale)
    return quotazione_attuale