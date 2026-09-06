"""Accesso al database per le entita' condivise fra piu' blueprint.

Le funzioni pure che stavano qui (ordinamento dei ruoli, formattazione
delle date) sono ora in app/domini/ruoli.py e app/core/tempo.py.
Il resto diventera' app/repositories/ nella prossima fase.
"""

from app.core.tempo import oggi
from psycopg2.extras import RealDictCursor

from app.core.logging import get_logger

logger = get_logger(__name__)

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


def get_crediti_e_offerta(conn, nome_squadra):
    """Crediti squadra e offerta totale in aste attive, in un'unica query
    (evita 2 round-trip separati al DB, usati insieme in ogni pagina asta)."""

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT
                    (SELECT crediti FROM squadra WHERE nome = %s) AS crediti,
                    (SELECT COALESCE(SUM(ultima_offerta), 0) FROM asta
                        WHERE squadra_vincente = %s AND stato = 'in_corso') AS offerta_totale;
    ''', (nome_squadra, nome_squadra))
    row = cur.fetchone()
    cur.close()
    return row["crediti"], row["offerta_totale"]


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
    """Slot giocatori (con contratto) + slot aste attive, in un'unica query
    invece di 2 round-trip separati."""

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT
                    (SELECT COUNT(id) FROM giocatore
                        WHERE squadra_att = %s
                            AND tipo_contratto IN ('Hold', 'Indeterminato')) AS slot_giocatori,
                    (SELECT COUNT(id) FROM asta
                        WHERE %s = ANY(partecipanti)
                            AND stato <> 'conclusa') AS slot_aste;
    ''', (nome_squadra, nome_squadra))
    row = cur.fetchone()
    cur.close()
    return row["slot_giocatori"] + row["slot_aste"]



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
    cur.close()
    
    return quotazione_attuale




def get_nome_giocatore(conn, id_giocatore):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT nome 
                FROM giocatore 
                WHERE id = %s;
    ''', (id_giocatore,))
    nome_giocatore = cur.fetchone()['nome']
    cur.close()

    return nome_giocatore

def decadi_vetrina(cur, giocatore_ids):
    """Rimuove dalla vetrina i giocatori indicati, se presenti (es. dopo svincolo, prestito, riscatto o scambio)."""
    if not isinstance(giocatore_ids, (list, tuple, set)):
        giocatore_ids = [giocatore_ids]
    giocatore_ids = [int(g) for g in giocatore_ids if g]
    if not giocatore_ids:
        return

    cur.execute('''
                DELETE FROM vetrina
                WHERE id_giocatore = ANY(%s);
    ''', (giocatore_ids,))


def get_general_config(conn):

    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('''
                SELECT mercato_chiusura, aste_chiusura
                FROM general_config
                WHERE id = 1;
    ''')
    config = cur.fetchone()
    cur.close()
    return config


def mercato_aperto(conn):
    """True se il mercato scambi (scambi e prestiti) è ancora aperto, in base alla
    data di chiusura impostata dall'admin (chiuso a partire dalla mezzanotte, ora di Roma,
    del giorno scelto). Nessuna data impostata = sempre aperto."""

    config = get_general_config(conn)
    chiusura = config["mercato_chiusura"] if config else None
    if chiusura is None:
        return True
    return oggi() < chiusura


def aste_aperte(conn):
    """True se le aste sono ancora aperte, in base alla data di chiusura impostata
    dall'admin (chiuse a partire dalla mezzanotte, ora di Roma, del giorno scelto).
    Nessuna data impostata = sempre aperte."""

    config = get_general_config(conn)
    chiusura = config["aste_chiusura"] if config else None
    if chiusura is None:
        return True
    return oggi() < chiusura


def get_stato_gate(conn):
    """Stato completo del gate mercato/aste (date di chiusura configurate e se le
    sezioni sono attualmente aperte), in un'unica query: usato dalle pagine menu
    per mostrare le voci come disabilitate con la data di chiusura in tooltip."""

    config = get_general_config(conn)
    mercato_chiusura = config["mercato_chiusura"] if config else None
    aste_chiusura = config["aste_chiusura"] if config else None
    data_odierna = oggi()

    return {
        "mercato_chiusura": mercato_chiusura,
        "mercato_aperto": mercato_chiusura is None or data_odierna < mercato_chiusura,
        "aste_chiusura": aste_chiusura,
        "aste_aperte": aste_chiusura is None or data_odierna < aste_chiusura,
    }


def sposta_crediti (conn, squadra_from, squadra_to, crediti):
    try:
        cur = conn.cursor()

        # Sottrarre crediti dalla squadra_from
        cur.execute('''
                    UPDATE squadra
                    SET crediti = crediti - %s
                    WHERE nome = %s;
        ''', (crediti, squadra_from))

        # Aggiungere crediti alla squadra_to
        cur.execute('''
                    UPDATE squadra
                    SET crediti = crediti + %s
                    WHERE nome = %s;
        ''', (crediti, squadra_to))

        conn.commit()

    except Exception as e:
        logger.exception("Errore durante lo spostamento dei crediti")
        conn.rollback()

    finally:
        cur.close()


