"""Giocatori: anagrafica e conteggi di rosa."""

# Contratti che occupano uno slot in rosa. Prestiti e primavera non contano.
CONTRATTI_CHE_OCCUPANO_SLOT = ('Hold', 'Indeterminato')


def nome(cur, id_giocatore: int) -> str:
    cur.execute("SELECT nome FROM giocatore WHERE id = %s;", (id_giocatore,))
    return cur.fetchone()["nome"]


def quotazione(cur, id_giocatore: int) -> int:
    cur.execute("SELECT quot_att_mantra FROM giocatore WHERE id = %s;", (id_giocatore,))
    return int(cur.fetchone()["quot_att_mantra"])


def slot_occupati_da_giocatori(cur, nome_squadra: str) -> int:
    cur.execute(
        """SELECT COUNT(id) AS n FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto IN ('Hold', 'Indeterminato');""",
        (nome_squadra,),
    )
    return cur.fetchone()["n"]


def slot_prestiti_in(cur, nome_squadra: str) -> int:
    cur.execute(
        """SELECT COUNT(id) AS n FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto = 'Fanta-Prestito';""",
        (nome_squadra,),
    )
    return cur.fetchone()["n"]


def nomi_per_id(cur, id_giocatori) -> dict[int, str]:
    """{id: nome} per un elenco di id, in una sola query.

    Risolve i nomi dei giocatori citati negli scambi senza interrogare il
    database una volta per scambio.
    """
    id_giocatori = [int(g) for g in (id_giocatori or []) if g]
    if not id_giocatori:
        return {}
    cur.execute("SELECT id, nome FROM giocatore WHERE id = ANY(%s);", (id_giocatori,))
    return {r["id"]: r["nome"] for r in cur.fetchall()}


def con_cartellino(cur, nome_squadra: str) -> list[dict]:
    """Giocatori di cui la squadra detiene il cartellino, primavera esclusa."""
    cur.execute(
        """SELECT id, nome, ruolo, club, quot_att_mantra FROM giocatore
           WHERE detentore_cartellino = %s AND tipo_contratto <> 'Primavera'
           ORDER BY nome;""",
        (nome_squadra,),
    )
    return cur.fetchall()


def primavera(cur, nome_squadra: str) -> list[dict]:
    cur.execute(
        """SELECT id, nome, ruolo, club, quot_att_mantra FROM giocatore
           WHERE squadra_att = %s AND tipo_contratto = 'Primavera';""",
        (nome_squadra,),
    )
    return cur.fetchall()


def chiamabili_in_asta(cur, soglia_u21: int | None) -> list[dict]:
    """Svincolati di prima fascia non gia' in asta.

    Gli U21 sono acquistabili solo tramite draft, quindi esclusi: sono i nati
    nell'anno di soglia o dopo. Nessuna soglia impostata, data di nascita non
    sincronizzata o ruolo di portiere = nessun filtro.
    """
    cur.execute(
        """SELECT nome, ruolo, club FROM giocatore AS g
           WHERE tipo_contratto = 'Svincolato' AND priorita = 1
             AND (%(soglia)s IS NULL
                  OR g.data_nascita IS NULL
                  OR EXTRACT(YEAR FROM g.data_nascita) < %(soglia)s
                  OR 'Por' = ANY(g.ruolo))
             AND NOT EXISTS (SELECT 1 FROM asta a
                             WHERE a.giocatore = g.id
                               AND a.stato IN ('mostra_interesse', 'in_corso'));""",
        {"soglia": soglia_u21})
    return cur.fetchall()


def prestabili_verso(cur, nome_squadra: str) -> list[dict]:
    """Giocatori richiedibili in prestito da questa squadra: esclude chi e' gia'
    in prestito, gli svincolati, e chi ha gia' una richiesta pendente da lei."""
    cur.execute(
        """SELECT id, nome, squadra_att, ruolo, club FROM giocatore g
           WHERE g.tipo_contratto <> 'Fanta-Prestito'
             AND g.squadra_att <> 'Svincolato'
             AND NOT EXISTS (SELECT 1 FROM prestito p
                             WHERE p.giocatore = g.id AND p.stato = 'in_attesa'
                               AND p.squadra_ricevente = %s);""",
        (nome_squadra,))
    return cur.fetchall()


def esiste_con_nome(cur, nome_giocatore: str) -> bool:
    """Confronto senza distinzione di maiuscole: due giocatori con lo stesso
    nome scritto diversamente sarebbero indistinguibili per gli utenti."""
    cur.execute("SELECT COUNT(*) AS n FROM giocatore WHERE LOWER(nome) = LOWER(%s);",
                (nome_giocatore,))
    return cur.fetchone()["n"] > 0


def id_per_nome_bloccando(cur, nome_giocatore: str) -> int | None:
    """Blocca la riga finche' la transazione non finisce: evita che due squadre
    aprano un'asta per lo stesso giocatore nello stesso istante."""
    cur.execute("SELECT id FROM giocatore WHERE nome = %s FOR UPDATE;", (nome_giocatore,))
    riga = cur.fetchone()
    return riga["id"] if riga else None


def assegna_in_prestito(cur, id_giocatore, squadra_ricevente: str) -> None:
    """Il giocatore passa alla squadra ricevente ma il cartellino resta a chi
    presta: e' la differenza fra un prestito e una cessione."""
    cur.execute(
        """UPDATE giocatore SET squadra_att = %s, tipo_contratto = 'Fanta-Prestito'
           WHERE id = %s;""", (squadra_ricevente, id_giocatore))


def collegati_alla_squadra(cur, nome_squadra: str) -> list[dict]:
    """Tutti i giocatori che la dashboard deve mostrare, in una query sola.

    La pagina ne elenca quattro gruppi - rosa, primavera, prestiti in entrata e
    in uscita - che prima erano quattro interrogazioni sulla stessa tabella con
    filtri diversi sulla stessa squadra. Ognuna costava un viaggio di rete.

    Qui si prendono insieme i giocatori che la squadra schiera (squadra_att) e
    quelli di cui detiene il cartellino pur non avendoli in rosa
    (detentore_cartellino, cioe' i prestiti in uscita), e la divisione nei
    quattro gruppi avviene in memoria.
    """
    cur.execute(
        """SELECT g.nome, g.tipo_contratto, g.ruolo, g.quot_att_mantra, g.costo, g.club,
                  g.squadra_att, g.detentore_cartellino, g.data_nascita, g.scadenza_contratto,
                  g.valore_mercato,
                  s.username AS squadra_username, d.username AS detentore_username
           FROM giocatore g
           LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
           LEFT JOIN squadra d ON d.nome = g.detentore_cartellino AND g.detentore_cartellino <> 'Svincolato'
           WHERE g.squadra_att = %s OR g.detentore_cartellino = %s;""",
        (nome_squadra, nome_squadra))
    return cur.fetchall()
