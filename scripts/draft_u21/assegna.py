"""
Registra l'esito del draft U21 a partire dal CSV delle scelte.

    python scripts/draft_u21/assegna.py --input draft_2027.csv
    python scripts/draft_u21/assegna.py --input draft_2027.csv --scrivi

Senza --scrivi non tocca niente: stampa l'abbinamento e fa rollback. Formato del
CSV, procedura di fine draft e difese stanno nel README qui accanto.
"""

import argparse
import csv
import sys
import textwrap
import unicodedata
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI.parents[1]))

from app.core import db  # noqa: E402


class DraftNonValido(Exception):
    """Il CSV non si aggancia al database: nessuna scrittura viene eseguita."""


def norm(testo):
    """"Cissè A." -> "cissea"."""
    piano = unicodedata.normalize("NFKD", str(testo)).encode("ascii", "ignore").decode()
    return "".join(c for c in piano.lower() if c.isalnum())


def ruoli(testo):
    """Ruoli come insieme: il CSV separa con lo spazio e scrive "Par", il database con la virgola e "Por"."""
    scritti = {norm(r) for r in str(testo).replace(",", " ").split() if r}
    return {"por" if r == "par" else r for r in scritti}


def anno_di(valore):
    """`draft.anno` è una data su alcune righe e un intero su altre."""
    return valore.year if hasattr(valore, "year") else valore


def leggi_foglio(percorso):
    """[(squadra, giro, ruolo, nome, punteggio)], letto per nome di colonna."""
    grezzo = Path(percorso).read_text(encoding="utf-8-sig")
    try:
        dialetto = csv.Sniffer().sniff(grezzo[:2000], delimiters=",;\t")
    except csv.Error:
        dialetto = csv.excel
    lettore = csv.DictReader(grezzo.splitlines(), dialect=dialetto)

    intestazione = {(c or "").strip().lower(): c for c in (lettore.fieldnames or [])}
    mancanti = [c for c in ("squadra", "pick", "ruolo", "calciatore") if c not in intestazione]
    if mancanti:
        raise DraftNonValido(
            f"{percorso}: mancano le colonne {mancanti}. "
            f"Trovate: {list(intestazione)}")

    def campo(riga, nome):
        return (riga.get(intestazione[nome]) or "").strip() if nome in intestazione else ""

    righe = []
    for riga in lettore:
        squadra, nome = campo(riga, "squadra"), campo(riga, "calciatore")
        if not (squadra and nome):
            continue
        pick = campo(riga, "pick")
        try:
            giro = int(pick)
        except ValueError:
            raise DraftNonValido(f"{nome} ({squadra}): pick {pick!r} non è un numero di giro")
        righe.append((squadra, giro, campo(riga, "ruolo"), nome, campo(riga, "punteggio") or None))
    if not righe:
        raise DraftNonValido(f"{percorso}: nessuna riga di draft trovata")
    return righe


def abbina_squadra(scritta, squadre):
    """"Zero Dayz" -> "ZeroDayz FC": uguale, oppure una contiene l'altra."""
    n = norm(scritta)
    for nome in squadre:
        if norm(nome) == n:
            return nome
    vicine = [nome for nome in squadre if n in norm(nome) or norm(nome) in n]
    if len(vicine) != 1:
        raise DraftNonValido(
            f"fantasquadra non riconosciuta: {scritta!r} (candidate: {vicine or 'nessuna'})")
    return vicine[0]


def abbina_giocatore(scritto, svincolati):
    n = norm(scritto)
    candidati = [g for g in svincolati if norm(g["nome"]) == n]
    if len(candidati) == 1:
        return candidati[0]
    if not candidati:
        raise DraftNonValido(
            f"{scritto!r} non è fra gli svincolati: correggi il nome nel CSV con quello "
            f"per esteso della lega, oppure il giocatore ha già una squadra")
    raise DraftNonValido(f"{scritto!r} corrisponde a più svincolati: {[g['id'] for g in candidati]}")


def carica_stato(cur):
    cur.execute("SELECT nome FROM squadra ORDER BY nome;")
    squadre = [r[0] for r in cur.fetchall()]

    cur.execute("""
        SELECT id, nome, ruolo FROM giocatore
        WHERE tipo_contratto = 'Svincolato';
    """)
    svincolati = [{"id": r[0], "nome": r[1], "ruolo": (r[2] or "").strip("{}")}
                  for r in cur.fetchall()]

    cur.execute("""
        SELECT id, anno, giro, numero, detentore_att
        FROM draft
        WHERE id_giocatore_scelto IS NULL
        ORDER BY anno, giro, numero;
    """)
    pick = [{"id": r[0], "anno": anno_di(r[1]), "giro": r[2],
             "numero": r[3], "squadra": r[4]} for r in cur.fetchall()]
    return squadre, svincolati, pick


def prepara(cur, righe, anno_scelto=None):
    """Chi va dove e con quale pick, o si ferma. Non scrive niente."""
    squadre, svincolati, pick_libere = carica_stato(cur)

    anni = sorted({p["anno"] for p in pick_libere if p["anno"] is not None})
    if anno_scelto is None:
        if not anni:
            raise DraftNonValido("non ci sono pick libere nella tabella draft")
        anno_scelto = anni[0]   # il draft in corso è il più vecchio ancora da usare
        quante = sum(1 for p in pick_libere if p["anno"] == anno_scelto)
        print(f"Draft {anno_scelto}: {quante} pick ancora libere "
              f"(è il primo anno non ancora giocato; con --anno se ne sceglie un altro)")

    libere = {}
    for p in pick_libere:
        if p["anno"] == anno_scelto:
            libere.setdefault((p["squadra"], p["giro"]), []).append(p)

    scelte, visti = [], {}
    for squadra_scritta, giro, ruolo_foglio, nome_scritto, punteggio in righe:
        squadra = abbina_squadra(squadra_scritta, squadre)
        giocatore = abbina_giocatore(nome_scritto, svincolati)

        if giocatore["id"] in visti:
            raise DraftNonValido(
                f"{giocatore['nome']} è assegnato due volte: {visti[giocatore['id']]} e {squadra}")
        visti[giocatore["id"]] = squadra

        disponibili = libere.get((squadra, giro), [])
        if not disponibili:
            raise DraftNonValido(
                f"{squadra} non ha una pick libera del giro {giro} nel draft {anno_scelto} "
                f"(serviva per {giocatore['nome']})")
        scelta = disponibili.pop(0)

        # ruolo diverso = quasi sempre una colonna del CSV ordinata per conto suo
        if not ruoli(ruolo_foglio) <= ruoli(giocatore["ruolo"]):
            print(f"  ⚠  {giocatore['nome']}: ruolo {giocatore['ruolo']!r} nel database, "
                  f"{ruolo_foglio!r} nel foglio")

        scelte.append({"squadra": squadra, "giocatore": giocatore,
                       "pick": scelta, "punteggio": punteggio})
    return scelte, anno_scelto


def scrivi(cur, scelte):
    # le WHERE ripetono lo stato letto in `prepara`: se qualcosa si è mosso nel
    # frattempo meglio perdere il run che assegnare mezzo draft
    for s in scelte:
        cur.execute("""
            UPDATE giocatore
            SET tipo_contratto = 'Primavera',
                squadra_att = %s,
                detentore_cartellino = %s
            WHERE id = %s AND tipo_contratto = 'Svincolato';
        """, (s["squadra"], s["squadra"], s["giocatore"]["id"]))
        if cur.rowcount != 1:
            raise DraftNonValido(
                f"{s['giocatore']['nome']} non risulta più svincolato: annullo tutto")

        cur.execute("""
            UPDATE draft
            SET id_giocatore_scelto = %s
            WHERE id = %s AND id_giocatore_scelto IS NULL;
        """, (s["giocatore"]["id"], s["pick"]["id"]))
        if cur.rowcount != 1:
            raise DraftNonValido(
                f"la pick giro {s['pick']['giro']} n.{s['pick']['numero']} di "
                f"{s['squadra']} risulta già usata: annullo tutto")


def testo_comunicazione(scelte, anno):
    """Una comunicazione sola, nella voce delle altre: una riga per squadra."""
    per_squadra = {}
    for s in scelte:
        per_squadra.setdefault(s["squadra"], []).append(s["giocatore"]["nome"])

    righe = [textwrap.dedent(f'''
        📢 COMUNICAZIONE UFFICIALE:
        Si è concluso il draft U21 {anno}.''').strip()]
    for squadra, giocatori in per_squadra.items():
        elenco = ", ".join(giocatori[:-1]) + " e " + giocatori[-1] \
            if len(giocatori) > 1 else giocatori[0]
        # "Varela G." finisce già col punto: il punto fermo ne farebbe due
        righe.append(f"La squadra {squadra} sceglie {elenco}" + ("" if elenco.endswith(".") else "."))
    return "\n".join(righe)


def annuncia(scelte, anno):
    from app import create_app
    from app import telegram_utils

    app = create_app()
    with app.app_context():
        # verso gruppo_comunicazioni `send_message` salva da sé la riga in
        # movimenti_squadra: annuncio e movimento sono lo stesso atto
        telegram_utils.send_message(nome_squadra="gruppo_comunicazioni",
                                    text_to_send=testo_comunicazione(scelte, anno))
        # l'invio passa da una coda con un thread daemon: senza aspettarla il
        # processo finisce prima che il messaggio parta
        telegram_utils._TELEGRAM_QUEUE.join()

    # a notifiche spente non parte niente, e non si salva nemmeno il movimento
    if telegram_utils.NOTIFICATIONS_ENABLED:
        print("Comunicazione inviata e movimento salvato.")
    else:
        print("Notifiche disattivate: nessuna comunicazione inviata e nessun "
              "movimento salvato (NOTIFICHE_ATTIVE=false).")


def main():
    ap = argparse.ArgumentParser(description="Registra l'esito del draft U21.")
    ap.add_argument("--input", required=True, help="il CSV con l'esito del draft")
    ap.add_argument("--scrivi", action="store_true",
                    help="esegue davvero le modifiche (senza, è una prova a vuoto)")
    ap.add_argument("--anno", type=int, default=None,
                    help="anno delle pick da consumare (default: il più vecchio ancora libero)")
    ap.add_argument("--senza-annuncio", action="store_true",
                    help="non manda la comunicazione Telegram e non salva il movimento")
    args = ap.parse_args()

    righe = leggi_foglio(args.input)
    db.init_pool()
    conn = cur = None
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        scelte, anno = prepara(cur, righe, args.anno)

        print()
        for s in scelte:
            p = s["pick"]
            print(f"  {s['squadra']:20} {s['giocatore']['nome']:18} id {s['giocatore']['id']:<5} "
                  f"pick giro {p['giro']} n.{p['numero']}"
                  + (f" · punteggio {s['punteggio']}" if s["punteggio"] is not None else ""))
        print(f"\n{len(scelte)} scelte, {len({s['squadra'] for s in scelte})} squadre, "
              f"draft {anno}.")
        print("\nComunicazione che verrà inviata:\n")
        print(textwrap.indent(testo_comunicazione(scelte, anno), "  "))

        if not args.scrivi:
            conn.rollback()
            print("\nProva a vuoto: niente è stato scritto. Rilancia con --scrivi.")
            return

        scrivi(cur, scelte)
        conn.commit()
        print("\n✅ Scritto: giocatori assegnati e pick consumate.")
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        db.release_connection(conn, cur)

    if not args.senza_annuncio:
        annuncia(scelte, anno)


if __name__ == "__main__":
    main()
