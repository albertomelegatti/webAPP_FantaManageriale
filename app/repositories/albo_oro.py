"""Albo d'oro: storico dei piazzamenti per stagione/competizione.

Una riga per squadra/posizione/fase/stagione. Puramente storica: i crediti
registrati qui sono già stati accreditati a suo tempo (es. via admin_crediti),
questa tabella si limita ad archiviarli per la bacheca pubblica. Popolata via
SQL a mano (vedi lo schema condiviso fuori dal repository) e, da qui, anche
dall'admin (pagina Albo d'Oro): le scritture non toccano mai i crediti delle
squadre, per lo stesso motivo.
"""


def leggi(cur) -> list[dict]:
    """Tutte le righe, dalla stagione più recente in giù.

    fase e' NULL per il Campionato: NULLS FIRST cosi' compare prima dei nomi
    di fase della Coppa nello stesso ordinamento.

    Dentro la Coppa le fasi finali vanno per prime. `fase` e' testo libero,
    quindi dal database non si ricava l'ordine in cui le fasi si giocano e
    l'unico criterio disponibile e' alfabetico. Con i nomi usati oggi
    ("Final 4", "Girone A", "Girone B") l'alfabetico basterebbe, perche' F
    viene prima di G; la condizione esplicita su "Final%" serve a non
    dipendere da quella coincidenza, e regge anche se domani una fase si
    chiamasse "Eliminatorie" o "Andata", che alfabeticamente precederebbero
    la finale.
    """
    cur.execute(
        """
        SELECT a.id, a.stagione, a.competizione, a.fase, a.squadra, a.posizione, a.crediti_generati,
               s.username
        FROM albo_oro a
        LEFT JOIN squadra s ON s.nome = a.squadra
        ORDER BY a.stagione DESC, a.competizione, (a.fase NOT ILIKE 'Final%%'), a.fase NULLS FIRST, a.posizione;
        """
    )
    return cur.fetchall()


def palmares(cur, nome_squadra: str) -> dict:
    """Le stagioni in cui la squadra ha vinto Campionato e Coppa.

    Un trofeo per stagione vinta (la pagina ne disegna uno per elemento della
    lista, col tooltip sulla stagione), non un conteggio. Vittoria = posizione
    1. Per il Campionato basta quello, perche' non ha fasi; per la Coppa serve
    anche restringere a una fase finale (stesso `ILIKE 'Final%%'` usato in
    leggi() per ordinarle), altrimenti il primo posto in un girone
    conterebbe come titolo.
    """
    cur.execute(
        """
        SELECT competizione, stagione
        FROM albo_oro
        WHERE squadra = %s
          AND posizione = 1
          AND (competizione = 'Campionato' OR fase ILIKE 'Final%%')
        ORDER BY stagione DESC;
        """,
        (nome_squadra,)
    )
    righe = cur.fetchall()
    return {
        "campionati": [r["stagione"] for r in righe if r["competizione"] == "Campionato"],
        "coppe": [r["stagione"] for r in righe if r["competizione"] == "Coppa"],
    }


def stagioni(cur) -> list[str]:
    """Le stagioni presenti, dalla piu' recente."""
    cur.execute("SELECT DISTINCT stagione FROM albo_oro ORDER BY stagione DESC;")
    return [r["stagione"] for r in cur.fetchall()]


def per_stagione(cur, stagione: str) -> list[dict]:
    """Le righe di una stagione, nello stesso ordine di leggi()."""
    cur.execute(
        """
        SELECT id, stagione, competizione, fase, squadra, posizione, crediti_generati
        FROM albo_oro
        WHERE stagione = %s
        ORDER BY competizione, (fase NOT ILIKE 'Final%%'), fase NULLS FIRST, posizione;
        """,
        (stagione,)
    )
    return cur.fetchall()


def sostituisci_stagione(cur, stagione: str, righe: list[dict]) -> None:
    """Riscrive tutti i piazzamenti di una stagione con quelli dati.

    Cancellare e reinserire (nella transazione del chiamante) invece di
    aggiornare riga per riga evita i conflitti transitori degli indici
    unici quando due squadre si scambiano la posizione.
    """
    cur.execute("DELETE FROM albo_oro WHERE stagione = %s;", (stagione,))
    for r in righe:
        cur.execute(
            """INSERT INTO albo_oro (stagione, competizione, fase, squadra, posizione, crediti_generati)
               VALUES (%s, %s, %s, %s, %s, %s);""",
            (stagione, r["competizione"], r["fase"], r["squadra"], r["posizione"], r["crediti_generati"]))


def classifica_campionato(cur, stagione: str) -> list[tuple[str, int]]:
    """[(squadra, posizione)] del Campionato di una stagione ("25-26").

    Serve a ordinare il draft: vuota se la stagione non e' stata ancora
    inserita nell'albo d'oro (dall'admin).
    """
    cur.execute(
        """SELECT squadra, posizione FROM albo_oro
           WHERE competizione = 'Campionato' AND stagione = %s
           ORDER BY posizione;""",
        (stagione,))
    return [(r["squadra"], r["posizione"]) for r in cur.fetchall()]
