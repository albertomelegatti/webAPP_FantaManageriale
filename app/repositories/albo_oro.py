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
