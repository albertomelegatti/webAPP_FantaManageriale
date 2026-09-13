"""Scambi: proposte di mercato fra due squadre."""


def per_squadra(cur, nome_squadra: str) -> list[dict]:
    """Tutte le proposte che coinvolgono la squadra, come proponente o come
    destinataria, dalla piu' recente."""
    cur.execute(
        """SELECT * FROM scambio
           WHERE squadra_proponente = %s OR squadra_destinataria = %s
           ORDER BY data_proposta DESC;""",
        (nome_squadra, nome_squadra),
    )
    return cur.fetchall()


def per_id(cur, id_scambio) -> dict | None:
    cur.execute("SELECT * FROM scambio WHERE id = %s;", (id_scambio,))
    return cur.fetchone()


def per_id_bloccando(cur, id_scambio) -> dict | None:
    """Come per_id(), ma blocca la riga: usata prima di decidere se lo scambio
    e' ancora eseguibile, cosi' due richieste concorrenti non lo processano
    entrambe."""
    cur.execute("SELECT * FROM scambio WHERE id = %s FOR UPDATE;", (id_scambio,))
    return cur.fetchone()


def in_attesa_bloccando(cur, id_scambio) -> dict | None:
    """Come per_id_bloccando(), filtrato a 'in_attesa': None se lo scambio non
    esiste o e' gia' stato deciso."""
    cur.execute("SELECT * FROM scambio WHERE id = %s AND stato = 'in_attesa' FOR UPDATE;", (id_scambio,))
    return cur.fetchone()


def annulla_concorrenti_per_giocatore(cur, id_giocatore, id_scambio_da_escludere) -> None:
    """Un giocatore appena spostato non puo' piu' essere oggetto di altre
    proposte in attesa: le annulla, tranne quella appena eseguita."""
    cur.execute(
        """UPDATE scambio SET stato = 'annullato'
           WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
             AND stato = 'in_attesa' AND id <> %s;""",
        (id_giocatore, id_giocatore, id_scambio_da_escludere))


def accetta(cur, id_scambio) -> None:
    cur.execute(
        "UPDATE scambio SET stato = 'accettato', data_risposta = NOW() AT TIME ZONE 'Europe/Rome' WHERE id = %s;",
        (id_scambio,))


def prestito_e_stato_bloccando(cur, id_scambio) -> dict | None:
    cur.execute(
        "SELECT prestito_associato, stato FROM scambio WHERE id = %s FOR UPDATE;",
        (id_scambio,))
    return cur.fetchone()


def annulla(cur, id_scambio) -> None:
    cur.execute("UPDATE scambio SET stato = 'annullato' WHERE id = %s;", (id_scambio,))


def solo_prestito_associato(cur, id_scambio) -> dict | None:
    cur.execute("SELECT prestito_associato FROM scambio WHERE id = %s;", (id_scambio,))
    return cur.fetchone()


def rifiuta(cur, id_scambio) -> None:
    cur.execute(
        "UPDATE scambio SET stato = 'rifiutato', data_risposta = NOW() AT TIME ZONE 'Europe/Rome' WHERE id = %s;",
        (id_scambio,))


def crea(cur, proponente: str, destinataria: str, crediti_offerti: int,
         crediti_richiesti: int, giocatori_offerti, giocatori_richiesti,
         pick_offerta, pick_richiesta, messaggio: str, prestiti_associati) -> int:
    cur.execute(
        """INSERT INTO scambio (squadra_proponente, squadra_destinataria,
                                crediti_offerti, crediti_richiesti,
                                giocatori_offerti, giocatori_richiesti,
                                pick_offerta, pick_richiesta,
                                messaggio, stato, data_proposta, prestito_associato)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'in_attesa',
                   NOW() AT TIME ZONE 'Europe/Rome', %s)
           RETURNING id;""",
        (proponente, destinataria, crediti_offerti, crediti_richiesti,
         giocatori_offerti, giocatori_richiesti, pick_offerta, pick_richiesta,
         messaggio, prestiti_associati or None))
    return cur.fetchone()["id"]
