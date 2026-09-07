"""Albo d'oro: storico dei piazzamenti per stagione/competizione.

Una riga per squadra/posizione/fase/stagione. Puramente storica: i crediti
registrati qui sono già stati accreditati a suo tempo (es. via admin_crediti),
questa tabella si limita ad archiviarli per la bacheca pubblica.
"""


def leggi(cur) -> list[dict]:
    """Tutte le righe, dalla stagione più recente in giù.

    fase e' NULL per il Campionato: NULLS FIRST cosi' compare prima dei nomi
    di fase della Coppa nello stesso ordinamento. Dentro la Coppa, le fasi il
    cui nome inizia per "Final" vanno sempre per prime (un ordinamento
    puramente alfabetico le metterebbe dopo "Girone A/B"): fase e' testo
    libero, quindi non c'e' un ordine cronologico vero e proprio da DB.
    """
    cur.execute(
        """
        SELECT id, stagione, competizione, fase, squadra, posizione, crediti_generati
        FROM albo_oro
        ORDER BY stagione DESC, competizione, (fase NOT ILIKE 'Final%%'), fase NULLS FIRST, posizione;
        """
    )
    return cur.fetchall()


def inserisci(cur, stagione: str, competizione: str, fase: str | None,
              squadra: str, posizione: int, crediti_generati: int) -> None:
    """Aggiunge una riga. Chi chiama gestisce psycopg2.errors.UniqueViolation
    (posizione o squadra già presente per quella fase/stagione/competizione)
    e il commit."""
    cur.execute(
        """
        INSERT INTO albo_oro (stagione, competizione, fase, squadra, posizione, crediti_generati)
        VALUES (%s, %s, %s, %s, %s, %s);
        """,
        (stagione, competizione, fase, squadra, posizione, crediti_generati),
    )


def elimina(cur, id_riga: int) -> None:
    cur.execute("DELETE FROM albo_oro WHERE id = %s;", (id_riga,))
