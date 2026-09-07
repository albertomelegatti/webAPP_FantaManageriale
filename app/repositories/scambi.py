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
