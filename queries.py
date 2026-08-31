import pytz
from datetime import datetime
from psycopg2.extras import RealDictCursor

ROME_TZ = pytz.timezone("Europe/Rome")

# Stesso ordine di ruoli già usato in produzione (vedi static/js/tables.js,
# RUOLO_PRIORITY): portieri, poi difensori, centrocampisti, esterni/trequartisti,
# infine attaccanti.
RUOLO_PRIORITY = {
    'POR': 1,
    'DD,E': 2,
    'DD,DC': 3,
    'DC': 4,
    'DD,DS,DC': 5,
    'DS,DC': 6,
    'DS,E': 7,
    'B,DD,E': 8,
    'B,DD,DS': 9,
    'B,DS,E': 10,
    'DD,DS,E': 11,
    'M,C': 12,
    'E': 13,
    'E,M': 14,
    'E,C': 15,
    'E,W': 16,
    'C,T': 17,
    'C': 18,
    'C,W,T': 19,
    'C,W': 20,
    'W': 21,
    'W,T': 22,
    'W,A': 23,
    'W,T,A': 24,
    'T,A': 25,
    'T': 26,
    'A': 27,
    'PC': 28,
}


def ruolo_sort_key(ruolo):
    chiave = ruolo.strip().upper().replace(' ', '')
    return RUOLO_PRIORITY.get(chiave, 99)


# Ordine dei ruoli base (singoli), stesso ordine POR -> difesa -> centrocampo
# -> esterni/trequartisti -> attacco usato per colorarli (vedi _macros.html)
RUOLI_BASE_ORDINE = ['Por', 'Dd', 'Ds', 'Dc', 'B', 'E', 'M', 'C', 'W', 'T', 'A', 'Pc']


def ruolo_base_sort_key(ruolo):
    try:
        return RUOLI_BASE_ORDINE.index(ruolo)
    except ValueError:
        return 99


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
    giocatore_ids = [g for g in giocatore_ids if g]
    if not giocatore_ids:
        return

    cur.execute('''
                DELETE FROM vetrina
                WHERE id_giocatore = ANY(%s);
    ''', (list(giocatore_ids),))


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
    return datetime.now(ROME_TZ).date() < chiusura


def aste_aperte(conn):
    """True se le aste sono ancora aperte, in base alla data di chiusura impostata
    dall'admin (chiuse a partire dalla mezzanotte, ora di Roma, del giorno scelto).
    Nessuna data impostata = sempre aperte."""

    config = get_general_config(conn)
    chiusura = config["aste_chiusura"] if config else None
    if chiusura is None:
        return True
    return datetime.now(ROME_TZ).date() < chiusura


def get_stato_gate(conn):
    """Stato completo del gate mercato/aste (date di chiusura configurate e se le
    sezioni sono attualmente aperte), in un'unica query: usato dalle pagine menu
    per mostrare le voci come disabilitate con la data di chiusura in tooltip."""

    config = get_general_config(conn)
    mercato_chiusura = config["mercato_chiusura"] if config else None
    aste_chiusura = config["aste_chiusura"] if config else None
    oggi = datetime.now(ROME_TZ).date()

    return {
        "mercato_chiusura": mercato_chiusura,
        "mercato_aperto": mercato_chiusura is None or oggi < mercato_chiusura,
        "aste_chiusura": aste_chiusura,
        "aste_aperte": aste_chiusura is None or oggi < aste_chiusura,
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
        print(f"Errore durante lo spostamento dei crediti: {e}")
        conn.rollback()
        
    finally:
        cur.close()