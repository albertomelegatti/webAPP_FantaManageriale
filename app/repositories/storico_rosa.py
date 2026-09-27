"""Storico delle rose: da quando ogni giocatore appartiene alla squadra che ne
detiene il cartellino (tabella giocatore_storico).

Le righe nascono e si chiudono da sole col trigger sul cambio di detentore
(vedi CronJob/giocatore_storico_schema.sql): l'applicazione scrive solo le
date di arrivo che non si sono potute ricostruire, dalla pagina admin.
"""

# Quanti movimenti proporre come suggerimento per ogni giocatore.
SUGGERIMENTI_PER_GIOCATORE = 3


def arrivi_da_completare(cur) -> list[dict]:
    """Le permanenze in corso senza data di arrivo, con gli ultimi movimenti
    che citano il giocatore e la sua squadra come suggerimento.

    Il suggerimento viene da una ricerca del nome nel testo libero dei
    movimenti: per questo non e' stato usato nella ricostruzione automatica, e
    qui resta una proposta che l'admin conferma o ignora.
    """
    cur.execute(
        """SELECT s.id, s.squadra, g.nome, g.ruolo, g.club, g.tipo_contratto,
                  COALESCE(sugg.movimenti, '[]'::json) AS suggerimenti
           FROM giocatore_storico s
           JOIN giocatore g ON g.id = s.giocatore
           LEFT JOIN LATERAL (
               SELECT json_agg(json_build_object('data', m.data, 'evento', m.evento)
                               ORDER BY m.data DESC, m.id DESC) AS movimenti
               FROM (
                   SELECT m.id, m.data, m.evento
                   FROM movimenti_squadra m
                   WHERE m.squadre @> ARRAY[s.squadra]::text[]
                     AND strpos(lower(m.evento), lower(g.nome)) > 0
                   ORDER BY m.data DESC, m.id DESC
                   LIMIT %s
               ) m
           ) sugg ON TRUE
           WHERE s.al IS NULL AND s.dal IS NULL
           ORDER BY s.squadra, g.nome;""",
        (SUGGERIMENTI_PER_GIOCATORE,))
    return cur.fetchall()


def imposta_arrivo(cur, id_riga: int, data_arrivo) -> bool:
    """Scrive la data di arrivo inserita dall'admin. Vale solo per una
    permanenza ancora aperta e senza data: se nel frattempo il giocatore e'
    stato ceduto o la data e' gia' stata inserita, non tocca nulla e
    restituisce False.

    La data diventa la mezzanotte in ora italiana "nominale", la stessa
    convenzione delle altre date dell'app.
    """
    cur.execute(
        """UPDATE giocatore_storico SET dal = %s::date::timestamp, fonte = 'admin'
           WHERE id = %s AND al IS NULL AND dal IS NULL;""",
        (data_arrivo, id_riga))
    return cur.rowcount == 1


def arrivi(cur, id_giocatori) -> dict:
    """{id_giocatore: dal} della permanenza in corso, in una sola query. Un
    giocatore senza permanenza aperta non compare; `dal` puo' essere None se la
    data non e' stata ancora completata da admin."""
    id_giocatori = [int(g) for g in (id_giocatori or []) if g]
    if not id_giocatori:
        return {}
    cur.execute(
        "SELECT giocatore, dal FROM giocatore_storico WHERE giocatore = ANY(%s) AND al IS NULL;",
        (id_giocatori,))
    return {r["giocatore"]: r["dal"] for r in cur.fetchall()}
