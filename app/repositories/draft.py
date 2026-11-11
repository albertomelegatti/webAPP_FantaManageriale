"""Pick del draft."""


def _anno(valore) -> str:
    """Il campo anno e' una data sul database ma viene mostrato come solo anno."""
    if valore is None:
        return "N/D"
    return str(valore.year if hasattr(valore, "year") else valore)


def descrizioni_per_id(cur, pick_ids) -> dict[int, str]:
    """{id: '2027 - Giro: 1°'} per un elenco di pick, in una sola query.

    Prima ogni riga di scambio interrogava il draft due volte, una per le pick
    offerte e una per quelle richieste.
    """
    pick_ids = [int(p) for p in (pick_ids or []) if p]
    if not pick_ids:
        return {}

    cur.execute(
        """SELECT id, anno, giro, numero FROM draft
           WHERE id = ANY(%s) ORDER BY anno, giro, numero;""",
        (pick_ids,),
    )
    return {r["id"]: f"{_anno(r['anno'])} - Giro: {r['giro']}°" for r in cur.fetchall()}


def disponibili(cur) -> list[dict]:
    """Le pick non ancora usate per scegliere un giocatore, per la pagina di
    nuovo scambio."""
    cur.execute(
        """SELECT id, anno, giro, numero, detentore_att, detentore_originale
           FROM draft WHERE id_giocatore_scelto IS NULL
           ORDER BY anno, giro, numero;""")
    return cur.fetchall()


def trasferisci(cur, id_pick, nuovo_detentore: str) -> None:
    cur.execute("UPDATE draft SET detentore_att = %s WHERE id = %s;", (nuovo_detentore, id_pick))


def esistono_tutte(cur, pick_ids) -> bool:
    """Verifica che ogni id corrisponda a una pick reale, prima di accettarla
    in una proposta di scambio."""
    pick_ids = [int(p) for p in (pick_ids or []) if p]
    if not pick_ids:
        return True
    cur.execute("SELECT COUNT(*) AS n FROM draft WHERE id = ANY(%s);", (pick_ids,))
    return cur.fetchone()["n"] == len(set(pick_ids))


def pick_della_squadra(cur, nome_squadra: str) -> list[dict]:
    cur.execute(
        """SELECT d.detentore_originale, d.anno, d.numero,
                  g.nome AS giocatore_scelto, g.tipo_contratto, g.ruolo,
                  g.quot_att_mantra, g.costo, g.club, g.squadra_att,
                  g.detentore_cartellino, g.data_nascita, g.scadenza_contratto,
                  g.valore_mercato, g.id_fantacalcio,
                  s.username AS squadra_username, dc.username AS detentore_username
           FROM draft d
           LEFT JOIN giocatore g ON d.id_giocatore_scelto = g.id
           LEFT JOIN squadra s ON s.nome = g.squadra_att AND g.squadra_att <> 'Svincolato'
           LEFT JOIN squadra dc ON dc.nome = g.detentore_cartellino AND g.detentore_cartellino <> 'Svincolato'
           WHERE d.detentore_att = %s
           ORDER BY d.anno, d.numero;""",
        (nome_squadra,))
    return cur.fetchall()


def storico(cur) -> list[dict]:
    """Le scelte dei draft gia' svolti, per la pagina pubblica dello storico.

    Solo le pick usate: quelle degli anni futuri esistono gia' in tabella ma
    non hanno ancora un giocatore. La squadra che ha scelto e' il detentore
    della pick, non quello originale: se la pick e' stata scambiata, ha scelto
    chi l'aveva in mano. Il ruolo e' quello attuale del giocatore, l'unico
    salvato.
    """
    cur.execute(
        """SELECT d.anno, d.giro, d.numero, d.detentore_att AS squadra,
                  s.username, g.nome AS giocatore, g.ruolo, g.id_fantacalcio
           FROM draft d
           JOIN giocatore g ON g.id = d.id_giocatore_scelto
           LEFT JOIN squadra s ON s.nome = d.detentore_att
           ORDER BY d.anno DESC, d.numero, d.giro;""")
    return [{**r, "anno": _anno(r["anno"])} for r in cur.fetchall()]


# --- Draft live ---------------------------------------------------------------
# `draft.anno` e' una data (1 gennaio): qui l'anno e' un intero e si confronta
# con EXTRACT, cosi' non importa se qualche riga ha un'altra data nell'anno.

def pick_dell_anno(cur, anno: int) -> list[dict]:
    """Tutte le pick di un draft, in ordine di chiamata (quelle senza numero in fondo)."""
    cur.execute(
        """SELECT id, giro, numero, detentore_att, detentore_originale,
                  id_giocatore_scelto, saltata, scelta_il, scelta_da
           FROM draft WHERE EXTRACT(YEAR FROM anno) = %s
           ORDER BY numero NULLS LAST, giro, id;""",
        (anno,))
    return cur.fetchall()


def assegna_numeri(cur, anno: int, ordine: list[dict]) -> None:
    """Scrive `numero` su ogni pick, secondo `ordine` ([{numero, giro, squadra}]).

    La pick si trova per giro e detentore ORIGINALE: e' la squadra che ha
    chiuso in quella posizione, anche se poi la pick e' stata scambiata (chi
    sceglie e' `detentore_att`, che qui non si tocca).

    Si ferma, senza scrivere niente di parziale (il chiamante annulla la
    transazione), se un draft e' gia' iniziato o se una pick non si trova.
    Prima i numeri vengono azzerati: rigenerare l'ordine scambierebbe numeri
    fra righe e l'indice unico (anno, numero) lo vieterebbe a meta' strada.
    """
    cur.execute(
        """SELECT COUNT(*) AS n FROM draft
           WHERE EXTRACT(YEAR FROM anno) = %s
             AND (id_giocatore_scelto IS NOT NULL OR saltata);""",
        (anno,))
    if cur.fetchone()["n"]:
        raise ValueError(f"Il draft {anno} e' gia' iniziato: l'ordine non si puo' rigenerare.")

    cur.execute("UPDATE draft SET numero = NULL WHERE EXTRACT(YEAR FROM anno) = %s;", (anno,))
    for p in ordine:
        cur.execute(
            """UPDATE draft SET numero = %s
               WHERE EXTRACT(YEAR FROM anno) = %s AND giro = %s AND detentore_originale = %s;""",
            (p["numero"], anno, p["giro"], p["squadra"]))
        if cur.rowcount != 1:
            raise ValueError(
                f"Draft {anno}: {cur.rowcount} pick per {p['squadra']} al giro {p['giro']}, "
                f"ne serve esattamente una.")


def pick_in_corso(cur, anno: int) -> dict | None:
    """La pick "on the clock": il numero piu' basso non ancora usato ne' saltato.

    Non c'e' un puntatore salvato: lo ricava la query, cosi' non puo' andare
    fuori sincrono con la tabella. None se l'ordine non e' stato generato o
    il draft e' finito.
    """
    cur.execute(
        """SELECT id, giro, numero, detentore_att, detentore_originale
           FROM draft
           WHERE EXTRACT(YEAR FROM anno) = %s
             AND numero IS NOT NULL
             AND id_giocatore_scelto IS NULL AND NOT saltata
           ORDER BY numero LIMIT 1;""",
        (anno,))
    return cur.fetchone()


def blocca_pick(cur, id_pick: int) -> dict | None:
    """Rilegge una pick prendendone il lock di riga fino a fine transazione.

    Due scelte quasi simultanee sulla stessa pick si mettono in fila: la
    seconda aspetta, poi la rilegge e la trova gia' usata.
    """
    cur.execute(
        """SELECT id, EXTRACT(YEAR FROM anno)::int AS anno, giro, numero,
                  detentore_att, detentore_originale, id_giocatore_scelto, saltata
           FROM draft WHERE id = %s FOR UPDATE;""",
        (id_pick,))
    return cur.fetchone()


def usa_pick(cur, id_pick: int, id_giocatore: int, da: str) -> bool:
    """Registra la scelta. False se la pick non era piu' libera."""
    cur.execute(
        """UPDATE draft
           SET id_giocatore_scelto = %s, scelta_il = now(), scelta_da = %s
           WHERE id = %s AND id_giocatore_scelto IS NULL AND NOT saltata;""",
        (id_giocatore, da, id_pick))
    return cur.rowcount == 1


def salta_pick(cur, id_pick: int, da: str) -> bool:
    """La pick e' persa (slot pieni) o saltata dall'admin. False se non era libera."""
    cur.execute(
        """UPDATE draft SET saltata = true, scelta_il = now(), scelta_da = %s
           WHERE id = %s AND id_giocatore_scelto IS NULL AND NOT saltata;""",
        (da, id_pick))
    return cur.rowcount == 1
