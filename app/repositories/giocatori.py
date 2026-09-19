"""Giocatori: anagrafica e conteggi di rosa."""

# Contratti che occupano uno slot in rosa. Prestiti e primavera non contano.
CONTRATTI_CHE_OCCUPANO_SLOT = ('Hold', 'Indeterminato')


def scambiabili(cur) -> list[dict]:
    """Giocatori proponibili in uno scambio: assegnati a una squadra, non in
    prestito ne' in hold."""
    cur.execute(
        """SELECT id, nome, squadra_att, tipo_contratto, ruolo, club
           FROM giocatore
           WHERE squadra_att IS NOT NULL
             AND squadra_att != 'Svincolati'
             AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold')
           ORDER BY squadra_att, nome;""")
    return cur.fetchall()


def trasferisci_cartellino(cur, id_giocatore: int, nuova_squadra: str) -> None:
    """Un giocatore scambiato: cartellino e squadra attuale vanno entrambi
    alla squadra che lo riceve. Valido solo per giocatori non in prestito ne'
    in hold, che non possono essere proposti in uno scambio."""
    cur.execute(
        "UPDATE giocatore SET detentore_cartellino = %s, squadra_att = %s WHERE id = %s;",
        (nuova_squadra, nuova_squadra, id_giocatore))


def svincola(cur, id_giocatore: int, nuovo_contratto: str) -> None:
    """Contratto 'Svincolato': squadra attuale e detentore cartellino tornano
    entrambi a 'Svincolato'."""
    cur.execute(
        """UPDATE giocatore SET tipo_contratto = %s, squadra_att = 'Svincolato',
               detentore_cartellino = 'Svincolato' WHERE id = %s;""",
        (nuovo_contratto, id_giocatore))


def manda_in_prestito_reale(cur, id_giocatore: int, nuovo_contratto: str) -> None:
    """Contratto 'Prestito Reale': solo la squadra attuale torna a 'Svincolato',
    il detentore del cartellino resta invariato."""
    cur.execute(
        "UPDATE giocatore SET tipo_contratto = %s, squadra_att = 'Svincolato' WHERE id = %s;",
        (nuovo_contratto, id_giocatore))


def assegna_a_squadra(cur, id_giocatore: int, nuovo_contratto: str, squadra_att: str) -> None:
    """Contratto 'Indeterminato': la squadra attuale torna al detentore del
    cartellino, che ha fatto la richiesta."""
    cur.execute(
        "UPDATE giocatore SET tipo_contratto = %s, squadra_att = %s WHERE id = %s;",
        (nuovo_contratto, squadra_att, id_giocatore))


def cambia_tipo_contratto(cur, id_giocatore: int, nuovo_contratto: str) -> None:
    """Ogni altro tipo di contratto: cambia solo l'etichetta, nessun altro campo."""
    cur.execute("UPDATE giocatore SET tipo_contratto = %s WHERE id = %s;", (nuovo_contratto, id_giocatore))


def nome(cur, id_giocatore: int) -> str:
    cur.execute("SELECT nome FROM giocatore WHERE id = %s;", (id_giocatore,))
    return cur.fetchone()["nome"]


def tipo_contratto(cur, id_giocatore: int) -> str:
    cur.execute("SELECT tipo_contratto FROM giocatore WHERE id = %s;", (id_giocatore,))
    return cur.fetchone()["tipo_contratto"]


def dettaglio(cur, id_giocatore: int) -> dict | None:
    cur.execute(
        "SELECT nome, tipo_contratto, ruolo, club FROM giocatore WHERE id = %s;",
        (id_giocatore,))
    return cur.fetchone()


def id_e_nome_con_cartellino(cur, nome_squadra: str) -> list[dict]:
    """Id e nome dei giocatori il cui cartellino appartiene alla squadra, per
    validare le righe inviate dalla pagina vetrina."""
    cur.execute("SELECT id, nome FROM giocatore WHERE detentore_cartellino = %s;", (nome_squadra,))
    return cur.fetchall()


def con_stato_vetrina(cur, nome_squadra: str) -> list[dict]:
    """Giocatori il cui cartellino appartiene alla squadra, con lo stato
    vetrina se presente. A differenza di con_cartellino() qui la Primavera non
    e' esclusa: la pagina vetrina la mostra insieme al resto della rosa."""
    cur.execute(
        """SELECT g.id, g.nome, g.ruolo, g.club, g.quot_att_mantra, g.tipo_contratto,
                  v.stato AS stato_vetrina, v.note AS note
           FROM giocatore g
           LEFT JOIN vetrina v ON v.id_giocatore = g.id
           WHERE g.detentore_cartellino = %s
           ORDER BY g.nome;""",
        (nome_squadra,))
    return cur.fetchall()


def trasferisci_dopo_riscatto(cur, id_giocatore: int, nome_squadra: str) -> None:
    """Il giocatore riscattato diventa di proprieta' della squadra che paga:
    squadra attuale e detentore del cartellino coincidono."""
    cur.execute(
        """UPDATE giocatore SET squadra_att = %s, detentore_cartellino = %s,
               tipo_contratto = 'Indeterminato' WHERE id = %s;""",
        (nome_squadra, nome_squadra, id_giocatore))


def trasferisci_da_prestito(cur, id_giocatore: int, nome_squadra: str) -> None:
    """Fine di un prestito: il giocatore torna alla squadra prestante, che ne
    era gia' il detentore del cartellino."""
    cur.execute(
        "UPDATE giocatore SET squadra_att = %s, tipo_contratto = 'Indeterminato' WHERE id = %s;",
        (nome_squadra, id_giocatore))


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


def crea_placeholder(cur, nome: str, club: str) -> int:
    """Crea un giocatore segnaposto, non ancora sincronizzato con Transfermarkt.

    Ruolo, quotazione e contratto sono valori fittizi in attesa
    dell'aggiornamento: e' il percorso usato quando si vuole mettere in asta
    un giocatore non ancora presente nel database.
    """
    cur.execute(
        """INSERT INTO giocatore (
               nome, ruolo, tipo_contratto, squadra_att, detentore_cartellino,
               quot_att_mantra, costo, priorita, club
           )
           VALUES (%s, ARRAY['PlaceHolderRole']::ruolo_mantra[], 'Svincolato', 'Svincolato', 'Svincolato', 666, 0, 1, %s)
           RETURNING id;""",
        (nome, club))
    return cur.fetchone()["id"]


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


def dettagli_per_id(cur, id_giocatori) -> dict[int, dict]:
    """{id: {nome, ruolo, data_nascita}} per un elenco di id, in una sola query.

    Come nomi_per_id, ma con i dati che servono ai messaggi Telegram per
    mostrare ruolo ed età accanto al nome.
    """
    id_giocatori = [int(g) for g in (id_giocatori or []) if g]
    if not id_giocatori:
        return {}
    cur.execute("SELECT id, nome, ruolo, data_nascita FROM giocatore WHERE id = ANY(%s);", (id_giocatori,))
    return {r["id"]: {"nome": r["nome"], "ruolo": r["ruolo"], "data_nascita": r["data_nascita"]}
            for r in cur.fetchall()}


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


def listone(cur) -> list[dict]:
    """Le righe del listone per la pagina: prima fascia, dal piu' quotato.

    Differisce da per_export_listone() perche' la pagina mostra anche gli
    username delle squadre, che servono a comporre i loghi: l'export, che e' un
    foglio di calcolo, non ne ha bisogno. Filtro e ordinamento sono gli stessi,
    cosi' export e pagina restano allineati.
    """
    cur.execute(
        """SELECT g.nome, g.ruolo, g.club, g.squadra_att, g.tipo_contratto,
                  g.quot_att_mantra, g.costo, g.detentore_cartellino,
                  s.username AS squadra_username, d.username AS detentore_username,
                  g.data_nascita, g.scadenza_contratto, g.valore_mercato
           FROM giocatore g
           LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
           LEFT JOIN squadra d ON d.nome = g.detentore_cartellino AND g.detentore_cartellino <> 'Svincolato'
           WHERE g.priorita = 1
           ORDER BY g.quot_att_mantra DESC;""")
    return cur.fetchall()


def per_export_listone(cur) -> list[dict]:
    """Le righe del listone da esportare in Excel, valori grezzi.

    Stesso filtro e ordinamento della pagina (solo priorita' 1, per
    quotazione decrescente), cosi' l'export corrisponde a quello che l'utente
    sta guardando.
    """
    cur.execute(
        """SELECT nome, squadra_att, detentore_cartellino, club, quot_att_mantra,
                  tipo_contratto, ruolo, costo, scadenza_contratto, data_nascita,
                  valore_mercato
           FROM giocatore
           WHERE priorita = 1
           ORDER BY quot_att_mantra DESC;""")
    return cur.fetchall()


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
        """SELECT g.id, g.nome, g.tipo_contratto, g.ruolo, g.quot_att_mantra, g.costo, g.club,
                  g.squadra_att, g.detentore_cartellino, g.data_nascita, g.scadenza_contratto,
                  g.valore_mercato, g.id_fantacalcio,
                  s.username AS squadra_username, d.username AS detentore_username
           FROM giocatore g
           LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
           LEFT JOIN squadra d ON d.nome = g.detentore_cartellino AND g.detentore_cartellino <> 'Svincolato'
           WHERE g.squadra_att = %s OR g.detentore_cartellino = %s;""",
        (nome_squadra, nome_squadra))
    return cur.fetchall()


def occupazione_slot(cur) -> list[dict]:
    """Slot occupati (Hold/Indeterminato) e slot in prestito, per squadra.

    Include solo le squadre con almeno un giocatore Hold/Indeterminato: e' lo
    stesso filtro che il template applica per decidere se mostrare la cella, e
    va preservato esattamente. Diversa da slot_per_squadra() qui sotto, che
    include tutte le squadre e serve al servizio mercato: unificarle
    cambierebbe quali squadre compaiono nella pagina crediti/stadi/slot.
    """
    cur.execute("""SELECT squadra_att, COUNT(id) AS slot_occupati
                   FROM giocatore
                   WHERE tipo_contratto IN ('Hold', 'Indeterminato')
                   GROUP BY squadra_att;""")
    slot_raw = cur.fetchall()

    cur.execute("""SELECT squadra_att, COUNT(id) AS slot_in_prestito
                   FROM giocatore
                   WHERE tipo_contratto = 'Fanta-Prestito'
                   GROUP BY squadra_att;""")
    prestiti = {r["squadra_att"]: r["slot_in_prestito"] for r in cur.fetchall()}

    return [
        {"squadra_att": r["squadra_att"], "slot_occupati": r["slot_occupati"],
         "slot_in_prestito": prestiti.get(r["squadra_att"], 0)}
        for r in slot_raw
    ]


def slot_per_squadra(cur) -> dict[str, dict]:
    """{squadra: {"giocatori": n, "prestiti": n}} per tutte le squadre.

    I due conteggi erano due scansioni della stessa tabella raggruppate sulla
    stessa colonna, con soli filtri di contratto diversi: un'aggregazione
    condizionale li fa insieme, in un viaggio di rete invece di due.
    """
    cur.execute(
        """SELECT squadra_att,
                  COUNT(*) FILTER (WHERE tipo_contratto IN ('Hold', 'Indeterminato')) AS giocatori,
                  COUNT(*) FILTER (WHERE tipo_contratto = 'Fanta-Prestito') AS prestiti
           FROM giocatore GROUP BY squadra_att;""")
    return {r["squadra_att"]: {"giocatori": r["giocatori"], "prestiti": r["prestiti"]}
            for r in cur.fetchall()}
