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
    return offerta_totale