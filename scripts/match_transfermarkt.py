"""
Script standalone per abbinare i giocatori di `giocatore` ai profili scaricati
con transfermarkt-scraper (github.com/dcaribou/transfermarkt-scraper), per
recuperare data di nascita e scadenza contratto reale.

Non fa parte dell'app Flask: transfermarkt-scraper va eseguito a parte (è un
progetto Poetry indipendente) per produrre il file di input, seguendo la
pipeline della Serie A (sostituire <season> con la stagione corrente, es. 2026):

    python -m tfmkt confederations > confederations.json
    python -m tfmkt competitions -p confederations.json > competitions.json
    grep '"competition_type": "first_tier"' competitions.json \
        | grep '"country_code": "IT1"' > serie_a.json
    python -m tfmkt clubs -p serie_a.json -s <season> > clubs.json
    python -m tfmkt players -p clubs.json -s <season> > players.json

Poi questo script legge `players.json` da disco e aggiorna il DB:

    python scripts/match_transfermarkt.py --input players.json

La mappa club fantacalcio -> nome ufficiale Transfermarkt vive nella tabella
`transfermarkt_mappa_club` (CronJob/transfermarkt_matching_schema.sql), non è
hard-coded qui: se un nome cambia o un club viene promosso/retrocesso si
aggiorna quella tabella via SQL senza toccare questo script.

Ad ogni run, la tabella `transfermarkt_giocatori` viene svuotata e ripopolata per
intero col dump più recente (è insieme cache grezza e coda di revisione: vedi il
commento sulla tabella in CronJob/transfermarkt_matching_schema.sql). Per i
giocatori senza `id_transfermarkt` fa SOLO il match esatto (auto-commit se un solo
candidato, marca le righe come "in revisione" se 2+ o 0). Non tenta match fuzzy e
non scrive suggerimenti: è la pagina admin
(/admin/verifica_corrispondenze_giocatori) a calcolarli al volo dalla cache per i
giocatori "non trovati", mostrandoli solo in revisione senza mai persisterli finché
l'admin non li conferma.

Per i giocatori che hanno GIÀ un `id_transfermarkt` (assegnato in un run precedente,
a mano o in automatico), lo script aggiorna solo `data_nascita`/`scadenza_contratto`
se cambiati nel dump più recente: `id_transfermarkt`, una volta trovato, non viene
mai più toccato. Pensato per essere lanciato periodicamente (es. una volta al
giorno) senza bisogno di supervisione.

Per proteggere un run non presidiato da uno scraping fallito/incompleto, lo script
si rifiuta di scrivere qualunque cosa (aborta con eccezione, nessuna modifica al DB)
se il dump ha troppi pochi giocatori o troppi pochi club rispetto all'atteso.
"""

import argparse
import json
import re
import sys

sys.path.insert(0, __file__.rsplit("/", 2)[0])

import db
from transfermarkt_matching import candidati_esatti, parse_data_tm

RE_ID_GIOCATORE = re.compile(r"/spieler/(\d+)")

# Oggi un dump completo di Serie A ha ~593 giocatori su 20 club: soglie larghe per
# non bloccare su piccole variazioni di rosa, ma abbastanza strette da bloccare
# su uno scraping palesemente fallito/incompleto.
SOGLIA_MINIMA_GIOCATORI = 400
MASSIMO_CLUB_MANCANTI = 2


class DumpNonAffidabile(Exception):
    """Il dump scaricato sembra incompleto/corrotto: nessuna scrittura viene eseguita."""


def carica_giocatori_transfermarkt(percorso_input):
    """Legge il dump JSON di transfermarkt-scraper e raggruppa per nome club TM."""
    per_club_tm = {}

    with open(percorso_input, encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            dato = json.loads(riga)

            match_id = RE_ID_GIOCATORE.search(dato.get("href") or "")
            if not match_id:
                continue

            club_tm = (dato.get("parent") or {}).get("name")
            cognome = dato.get("last_name") or dato.get("name") or ""

            per_club_tm.setdefault(club_tm, []).append({
                "id_transfermarkt": int(match_id.group(1)),
                "cognome": cognome,
                "nome": dato.get("name") or "",
                "nome_completo": f"{dato.get('name') or ''} {cognome}".strip(),
                "club_tm": club_tm,
                "data_nascita": parse_data_tm(dato.get("date_of_birth")),
                "scadenza_contratto": parse_data_tm(dato.get("contract_expires")),
            })

    return per_club_tm


def salva_cache(cur, giocatori_tm_per_club_tm):
    """Svuota transfermarkt_giocatori e la ripopola col dump più recente (tutti i
    giocatori partono come sola cache, id_giocatore NULL: i marcatori di revisione
    vengono rimessi dal resto di esegui_matching nella stessa transazione)."""
    cur.execute("TRUNCATE transfermarkt_giocatori;")
    for club_tm, giocatori in giocatori_tm_per_club_tm.items():
        for g in giocatori:
            cur.execute(
                """
                INSERT INTO transfermarkt_giocatori
                    (id_transfermarkt, club_tm, nome, cognome, data_nascita, scadenza_contratto)
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (g["id_transfermarkt"], club_tm, g["nome"], g["cognome"],
                 g["data_nascita"], g["scadenza_contratto"]),
            )


def aggiorna_gia_matchati(cur, per_id_transfermarkt):
    """Aggiorna data_nascita/scadenza_contratto dei giocatori già mappati in un run
    precedente, SENZA mai toccare id_transfermarkt: una volta trovato, resta fisso."""
    cur.execute(
        '''
        SELECT id, id_transfermarkt, data_nascita, scadenza_contratto
        FROM giocatore
        WHERE id_transfermarkt IS NOT NULL AND priorita = 1;
        '''
    )
    gia_matchati = cur.fetchall()

    n_aggiornati = 0
    for g in gia_matchati:
        aggiornato = per_id_transfermarkt.get(g["id_transfermarkt"])
        if not aggiornato:
            # Non più nella rosa scaricata (es. ha lasciato la Serie A): lascia i
            # dati com'erano piuttosto che cancellarli.
            continue
        if (aggiornato["data_nascita"] == g["data_nascita"]
                and aggiornato["scadenza_contratto"] == g["scadenza_contratto"]):
            continue

        cur.execute(
            '''
            UPDATE giocatore
            SET data_nascita = %s,
                scadenza_contratto = %s
            WHERE id = %s;
            ''',
            (aggiornato["data_nascita"], aggiornato["scadenza_contratto"], g["id"]),
        )
        n_aggiornati += 1

    return n_aggiornati


def esegui_matching(percorso_input):
    giocatori_tm_per_club_tm = carica_giocatori_transfermarkt(percorso_input)

    totale_giocatori = sum(len(v) for v in giocatori_tm_per_club_tm.values())
    if totale_giocatori < SOGLIA_MINIMA_GIOCATORI:
        raise DumpNonAffidabile(
            f"Solo {totale_giocatori} giocatori nel dump (attesi almeno {SOGLIA_MINIMA_GIOCATORI}): "
            "probabile scraping fallito o incompleto."
        )

    per_id_transfermarkt = {
        g["id_transfermarkt"]: g
        for giocatori in giocatori_tm_per_club_tm.values()
        for g in giocatori
    }

    n_auto = n_ambigui = n_non_trovati = 0

    with db.DatabaseConnection() as (conn, cur):
        cur.execute("SELECT club, nome_transfermarkt FROM transfermarkt_mappa_club;")
        mappa_club = {r["club"]: r["nome_transfermarkt"] for r in cur.fetchall()}

        club_mancanti = [nome for nome in mappa_club.values() if nome not in giocatori_tm_per_club_tm]
        if len(club_mancanti) > MASSIMO_CLUB_MANCANTI:
            raise DumpNonAffidabile(
                f"{len(club_mancanti)} club mancanti dal dump ({', '.join(club_mancanti)}): "
                "probabile scraping parziale."
            )

        salva_cache(cur, giocatori_tm_per_club_tm)
        n_aggiornati = aggiorna_gia_matchati(cur, per_id_transfermarkt)

        # priorita = 1: solo i giocatori attualmente in Serie A (priorita = 0 sono
        # svincolati/fuori rosa di club non più in Serie A, non cercabili su Transfermarkt
        # nelle rose attuali che scraperemo).
        cur.execute("SELECT id, nome, club FROM giocatore WHERE id_transfermarkt IS NULL AND priorita = 1;")
        nostri_giocatori = cur.fetchall()

        for giocatore in nostri_giocatori:
            club_tm = mappa_club.get(giocatore["club"])
            candidati = candidati_esatti(
                giocatore["nome"], giocatori_tm_per_club_tm.get(club_tm, [])
            )

            if len(candidati) == 1:
                c = candidati[0]
                cur.execute(
                    """
                    UPDATE giocatore
                    SET id_transfermarkt = %s,
                        data_nascita = %s,
                        scadenza_contratto = %s
                    WHERE id = %s;
                    """,
                    (c["id_transfermarkt"], c["data_nascita"], c["scadenza_contratto"], giocatore["id"]),
                )
                n_auto += 1

            elif len(candidati) >= 2:
                # Marca le righe di cache già inserite come candidati in revisione
                # per questo giocatore (niente righe duplicate: la tabella è stata
                # appena svuotata e ripopolata da salva_cache).
                cur.execute(
                    """
                    UPDATE transfermarkt_giocatori
                    SET id_giocatore = %s
                    WHERE id_transfermarkt = ANY(%s);
                    """,
                    (giocatore["id"], [c["id_transfermarkt"] for c in candidati]),
                )
                n_ambigui += 1

            else:
                # Riga sintetica "non trovato": nessun dato TM reale, solo il marcatore.
                cur.execute(
                    """
                    INSERT INTO transfermarkt_giocatori (id_giocatore, id_transfermarkt)
                    VALUES (%s, NULL);
                    """,
                    (giocatore["id"],),
                )
                n_non_trovati += 1

    print(f"🔄 Aggiornati (già mappati, dati cambiati): {n_aggiornati}")
    print(f"✅ Match automatico (nuovi): {n_auto}")
    print(f"⚠️  Ambigui (in revisione): {n_ambigui}")
    print(f"❌ Non trovati (in revisione, suggerimenti fuzzy calcolati dalla pagina admin): {n_non_trovati}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Abbina i giocatori a Transfermarkt.")
    parser.add_argument("--input", required=True, help="File JSON (newline-delimited) prodotto da transfermarkt-scraper (crawler players)")
    args = parser.parse_args()

    db.init_pool()
    esegui_matching(args.input)
