"""Albo d'oro: storico dei piazzamenti per stagione/competizione.

Una riga per squadra/posizione/fase/stagione. Puramente storica: i crediti
registrati qui sono già stati accreditati a suo tempo (es. via admin_crediti),
questa tabella si limita ad archiviarli per la bacheca pubblica. Popolata via
SQL a mano (vedi lo schema condiviso fuori dal repository), nessuna scrittura
da app.
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
        SELECT id, stagione, competizione, fase, squadra, posizione, crediti_generati
        FROM albo_oro
        ORDER BY stagione DESC, competizione, (fase NOT ILIKE 'Final%%'), fase NULLS FIRST, posizione;
        """
    )
    return cur.fetchall()
