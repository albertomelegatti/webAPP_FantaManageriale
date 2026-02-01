import psycopg2
from datetime import datetime, time
import telegram_utils
from psycopg2.extras import RealDictCursor
from flask import Blueprint, render_template, redirect, url_for, flash, request
from db import get_connection, release_connection
from user import format_giocatori, formatta_data
from queries import get_crediti_squadra, get_offerta_totale, get_slot_occupati, get_slot_prestiti_in


mercato_bp = Blueprint('mercato', __name__, url_prefix='/mercato')


@mercato_bp.route("/mercato/<nome_squadra>", methods=["GET", "POST"])
def user_mercato(nome_squadra):
    conn = None
    cur = None
    crediti = 0
    offerta_massima_possibile = 0

    try:
        conn = get_connection()
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_REPEATABLE_READ)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":

            # Bottone ANNULLA scambio
            scambio_id = request.form.get("annulla_scambio")
            if scambio_id:
                annulla_scambio(scambio_id, conn)


            # Bottone ACCETTA scambio
            scambio_id = request.form.get("accetta_scambio")
            if scambio_id:
                effettua_scambio(scambio_id, conn, nome_squadra)
                

            
            # Bottone RIFIUTA scambio
            scambio_id = request.form.get("rifiuta_scambio")
            if scambio_id:
                cur.execute("SELECT prestito_associato FROM scambio WHERE id = %s", (scambio_id,))
                scambio = cur.fetchone()

                cur.execute('''
                            UPDATE scambio
                            SET stato= 'rifiutato',
                                data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                            WHERE id = %s;
                ''', (scambio_id,))
                
                # Rifiuta anche i prestiti collegati
                if scambio and scambio['prestito_associato']:
                    cur.execute('''
                                UPDATE prestito
                                SET stato = 'rifiutato'
                                WHERE id = ANY(%s) AND stato = 'in_attesa';
                    ''', (scambio['prestito_associato'],))

                conn.commit()
                telegram_utils.scambio_risposta(conn, scambio_id, "Rifiutato")




        
        crediti = get_crediti_squadra(conn, nome_squadra)
        offerta_totale = get_offerta_totale(conn, nome_squadra)
        offerta_massima_possibile = crediti - offerta_totale

        # Scarico le informazioni sugli scambi della squadra loggata
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE squadra_proponente = %s
                    OR squadra_destinataria = %s
                    ORDER BY data_proposta DESC;
        ''', (nome_squadra, nome_squadra))
        scambi_raw = cur.fetchall()

        scambi = []
        for s_raw in scambi_raw:
            s_dict = dict(s_raw)
            # Add formatted player names for JS to use, without overwriting original IDs
            s_dict['giocatori_offerti_nomi'] = format_giocatori(s_dict['giocatori_offerti'])
            s_dict['giocatori_richiesti_nomi'] = format_giocatori(s_dict['giocatori_richiesti'])
            scambi.append(s_dict)
        
    except Exception as e:
        print("Errore:", e)
        flash("❌ Errore durante il caricamento degli scambi.", "danger")
        return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))

    finally:
        release_connection(conn, cur)

    return render_template("user_mercato.html", nome_squadra=nome_squadra, crediti=crediti, offerta_massima_possibile=offerta_massima_possibile, scambi=scambi)




@mercato_bp.route("/visualizza_proposta/<scambio_id>", methods=["GET", "POST"])
def visualizza_proposta(scambio_id):
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE id = %s;
        ''', (scambio_id,))
        scambio_raw = cur.fetchone()
        
        scambio = {
            "scambio_id": scambio_raw['id'],
            "squadra_proponente": scambio_raw['squadra_proponente'],
            "data_proposta": formatta_data(scambio_raw['data_proposta']),
            "messaggio": scambio_raw['messaggio'],
            "stato": scambio_raw['stato'],
            "crediti_offerti": scambio_raw['crediti_offerti'],
            "crediti_richiesti": scambio_raw['crediti_richiesti'],
            "giocatori_offerti": format_giocatori(scambio_raw['giocatori_offerti']),
            "giocatori_richiesti": format_giocatori(scambio_raw['giocatori_richiesti']),
            "prestito_associato": format_prestito(conn, scambio_raw['prestito_associato'])
        }
        
        return render_template("visualizza_proposta.html", scambio=scambio)
    
    except Exception as e:
        print("Errore:", e)
        flash("❌ Errore durante il caricamento della proposta.", "danger")

    finally:
        release_connection(conn, cur)
        
        













@mercato_bp.route("/nuovo_scambio/<nome_squadra>", methods=["GET", "POST"])
def nuovo_scambio(nome_squadra):
    conn = None
    cur = None

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        if request.method == "POST":
            squadra_destinataria = request.form.get("squadra_destinataria")
            crediti_offerti = int(request.form.get("crediti_offerti") or 0)
            crediti_richiesti = int(request.form.get("crediti_richiesti") or 0)
            giocatori_offerti = [int(g) for g in request.form.getlist("giocatori_offerti") if g.isdigit()]
            giocatori_richiesti = [int(g) for g in request.form.getlist("giocatori_richiesti") if g.isdigit()]
            messaggio = (request.form.get("messaggio") or "").strip()

            # Nuovi campi prestito (due blocchi opzionali)
            enable_prestito1 = request.form.get("enable_prestito1") is not None
            enable_prestito2 = request.form.get("enable_prestito2") is not None

            # Prestito 1
            p1_richiesto = request.form.get("prestito1_richiesto")
            p1_offerto = request.form.get("prestito1_offerto")
            p1_tipo_richiesto = (request.form.get("prestito1_tipo_richiesto") or "").strip()
            p1_tipo_offerto = (request.form.get("prestito1_tipo_offerto") or "").strip()
            p1_riscatto_rich = int(request.form.get("prestito1_riscatto_richiesto") or 0)
            p1_riscatto_off = int(request.form.get("prestito1_riscatto_offerto") or 0)

            # Prestito 2
            p2_richiesto = request.form.get("prestito2_richiesto")
            p2_offerto = request.form.get("prestito2_offerto")
            p2_tipo_richiesto = (request.form.get("prestito2_tipo_richiesto") or "").strip()
            p2_tipo_offerto = (request.form.get("prestito2_tipo_offerto") or "").strip()
            p2_riscatto_rich = int(request.form.get("prestito2_riscatto_richiesto") or 0)
            p2_riscatto_off = int(request.form.get("prestito2_riscatto_offerto") or 0)

            def map_tipo(val):
                if not val:
                    return ''
                elif val == 'Secco':
                    return 'secco'
                elif val in ('Con diritto di riscatto', 'Diritto'):
                    return 'diritto_di_riscatto'
                elif val in ('Con obbligo di riscatto', 'Obbligo'):
                    return 'obbligo_di_riscatto'
                return ''

            # Se secco, forza riscatto a 0
            if map_tipo(p1_tipo_richiesto) == 'secco':
                p1_riscatto_rich = 0
            if map_tipo(p1_tipo_offerto) == 'secco':
                p1_riscatto_off = 0
            if map_tipo(p2_tipo_richiesto) == 'secco':
                p2_riscatto_rich = 0
            if map_tipo(p2_tipo_offerto) == 'secco':
                p2_riscatto_off = 0

            # Data di fine default: 2 luglio alle 23:59:59 (prima data utile futura)
            today = datetime.now()
            target_year = today.year if today < datetime(today.year, 7, 2) else today.year + 1

            default_data_fine = datetime(target_year, 7, 2, 23, 59, 59)

            # Validazioni base
            if not squadra_destinataria:
                flash("Seleziona una squadra destinataria.", "warning")
                return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

            if not giocatori_offerti and crediti_offerti == 0:
                flash("Devi offrire almeno un giocatore o dei crediti.", "warning")
                return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))

            if not giocatori_richiesti and crediti_richiesti == 0:
                flash("Devi richiedere almeno un giocatore o dei crediti.", "warning")
                return redirect(url_for("mercato.nuovo_scambio", nome_squadra=nome_squadra))
            



            # Inserisci eventuali prestiti collegati (costo_prestito=0)
            def crea_prestito(giocatore_id, squadra_prestante, squadra_ricevente, tipo_txt, riscatto):

                if not giocatore_id or not tipo_txt:
                    return None
                
                tipo_db = map_tipo(tipo_txt)
                if tipo_db == 'secco':
                    riscatto = 0

                cur.execute('''
                    INSERT INTO prestito (
                        giocatore, squadra_prestante, squadra_ricevente, stato, data_inizio, data_fine, costo_prestito, tipo_prestito, crediti_riscatto, note
                    ) VALUES (%s, %s, %s, 'in_attesa', NOW() AT TIME ZONE 'Europe/Rome', %s, %s, %s, %s, %s)
                    RETURNING id;
                ''', (
                    int(giocatore_id),
                    squadra_prestante,
                    squadra_ricevente,
                    default_data_fine,
                    0,
                    tipo_db,
                    int(riscatto or 0),
                    ''
                ))
                return cur.fetchone()['id']
            
            
            


            created_prestiti = []

            if enable_prestito1:
                if p1_richiesto:
                    created_prestiti.append(
                        crea_prestito(p1_richiesto, squadra_destinataria, nome_squadra, p1_tipo_richiesto, p1_riscatto_rich)
                    )
                if p1_offerto:
                    created_prestiti.append(
                        crea_prestito(p1_offerto, nome_squadra, squadra_destinataria, p1_tipo_offerto, p1_riscatto_off)
                    )

            if enable_prestito2:
                if p2_richiesto:
                    created_prestiti.append(
                        crea_prestito(p2_richiesto, squadra_destinataria, nome_squadra, p2_tipo_richiesto, p2_riscatto_rich)
                    )
                if p2_offerto:
                    created_prestiti.append(
                        crea_prestito(p2_offerto, nome_squadra, squadra_destinataria, p2_tipo_offerto, p2_riscatto_off)
                    )


            if len(created_prestiti) == 0:
                created_prestiti = None


            # Inserisci la proposta di scambio
            cur.execute('''
                INSERT INTO scambio (
                    squadra_proponente, squadra_destinataria, 
                    crediti_offerti, crediti_richiesti, 
                    giocatori_offerti, giocatori_richiesti, 
                    messaggio, stato, data_proposta, prestito_associato
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'in_attesa', NOW() AT TIME ZONE 'Europe/Rome', %s)
                RETURNING id;
            ''', (
                nome_squadra,
                squadra_destinataria,
                crediti_offerti,
                crediti_richiesti,
                giocatori_offerti,
                giocatori_richiesti,
                messaggio,
                created_prestiti
            ))
            id_scambio = cur.fetchone()['id']

            conn.commit()


            flash("✅ Proposta inviata con successo!", "success")
            telegram_utils.nuovo_scambio(conn, id_scambio)

            return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))


        # Sezione GET

        # Recupera tutte le squadre (tranne "Svincolato")
        cur.execute('''
            SELECT nome, crediti 
            FROM squadra 
            WHERE nome <> 'Svincolato'
            ORDER BY nome;
        ''')
        squadre_raw = cur.fetchall()

        squadre = []
        crediti_effettivi = 0
        offerta_totale = get_offerta_totale(conn, nome_squadra)

        for s in squadre_raw:
            slot_occupati = int(get_slot_occupati(conn, s["nome"]))
            slot_prestiti = int(get_slot_prestiti_in(conn, s["nome"]))
            offerta_massima_possibile = max(s["crediti"] - offerta_totale, 0)

            squadre.append({
                "nome": s["nome"],
                "offerta_massima_possibile": offerta_massima_possibile,
                "slot_liberi": max(30 - slot_occupati, 0),
                "slot_prestiti": slot_prestiti
            })

            if s["nome"] == nome_squadra:
                crediti_effettivi = offerta_massima_possibile

        # Slot liberi e prestiti della squadra loggata
        slot_liberi_miei = max(30 - int(get_slot_occupati(conn, nome_squadra)), 0)
        slot_prestiti_miei = int(get_slot_prestiti_in(conn, nome_squadra))

        # Recupera tutti i giocatori validi (non svincolati, non prestiti, non hold)
        cur.execute('''
                SELECT id, nome, squadra_att, tipo_contratto
                FROM giocatore
                WHERE squadra_att IS NOT NULL
                    AND squadra_att != 'Svincolati'
                    AND tipo_contratto NOT IN ('Fanta-Prestito', 'Hold')
                ORDER BY squadra_att, nome;
        ''')
        giocatori_raw = cur.fetchall()

        miei_giocatori = [g for g in giocatori_raw if g["squadra_att"] == nome_squadra]
        giocatori = [
            {
                "id": g["id"],
                "nome": g["nome"],
                "squadra_att": g["squadra_att"],
                "tipo_contratto": g["tipo_contratto"]
            }
            for g in giocatori_raw
        ]

        return render_template(
            "user_nuovo_scambio.html",
            nome_squadra=nome_squadra,
            squadre=squadre,
            giocatori=giocatori,
            miei_giocatori=miei_giocatori,
            crediti_effettivi=crediti_effettivi,
            slot_liberi_miei=slot_liberi_miei,
            slot_prestiti_miei=slot_prestiti_miei
        )

    except Exception as e:
        print(f"Errore durante il caricamento di 'nuovo_scambio': {e}")
        flash("❌ Si è verificato un errore nel caricamento della pagina.", "danger")
        return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))

    finally:
        release_connection(conn, cur)



def controlla_scambio(id, conn):

    valido = True
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        # Recupero dati dello scambio
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE id = %s
                    FOR UPDATE;''', (id,))
        scambio = cur.fetchone()

        if scambio['stato'] != 'in_attesa':
            return False

        
        squadra_proponente = scambio["squadra_proponente"]
        squadra_destinataria = scambio["squadra_destinataria"]
        crediti_offerti = scambio["crediti_offerti"] or 0
        crediti_richiesti = scambio["crediti_richiesti"] or 0
        giocatori_offerti = scambio["giocatori_offerti"] or []
        giocatori_richiesti = scambio["giocatori_richiesti"] or []

        # Controllo che le squadre abbiano abbastanza crediti per effettuare lo scambio
        cur.execute('''
                    SELECT crediti 
                    FROM squadra 
                    WHERE nome = %s FOR UPDATE;
        ''', (squadra_proponente,))

        crediti_prop = cur.fetchone()["crediti"]
        
        offerta_tot_prop = get_offerta_totale(conn, squadra_proponente)
        crediti_disp_prop = crediti_prop - offerta_tot_prop
        

        cur.execute('''
                    SELECT crediti 
                    FROM squadra 
                    WHERE nome = %s FOR UPDATE;
        ''', (squadra_destinataria,))
        crediti_dest = cur.fetchone()["crediti"]
        
        offerta_tot_dest = get_offerta_totale(conn, squadra_destinataria)
        crediti_disp_dest = crediti_dest - offerta_tot_dest

        if crediti_disp_prop < crediti_offerti:
            return False
        
        if crediti_disp_dest < crediti_richiesti:
            return False
        
        # Controllo che le squadre abbiano abbastanza slot giocatori disponibili per effettuare gli scambi
        slot_squadra_proponente = get_slot_occupati(conn, squadra_proponente)
        slot_squadra_destinataria = get_slot_occupati(conn, squadra_destinataria)

        # Verifica post-scambio: slot occupati dopo aver applicato entrate/uscite
        slot_prop_finali = slot_squadra_proponente - len(giocatori_offerti) + len(giocatori_richiesti)
        slot_dest_finali = slot_squadra_destinataria - len(giocatori_richiesti) + len(giocatori_offerti)

        if slot_prop_finali > 30:
            return False

        if slot_dest_finali > 30:
            return False

        return True

    except Exception as e:
        print(f"Errore: {e}")
        return False

    finally:
        cur.close()





def effettua_scambio(id, conn, nome_squadra):

    # Se lo scambio non è valido non fare niente
    if controlla_scambio(id, conn) == False:
        flash("❌ Non è possibile avviare questo scambio.", "danger")
        return
    

    # Se lo scambio è valido, esegui tutti i passaggi.
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Recupero dati dello scambio
        cur.execute('''
                    SELECT *
                    FROM scambio
                    WHERE id = %s
                        AND stato = 'in_attesa'
                    FOR UPDATE;''', (id,))
        
        scambio = cur.fetchone()

        if not scambio:
            raise ValueError(f"Nessuno scambio valido trovato con id: {id}")
        
        # Controllo se lo scambio è stato annullato nel mentre che la pagina era aperta
        if scambio['stato'] != 'in_attesa':
            flash("Lo scambio non è più valido.", "danger")
            return redirect(url_for("mercato.user_mercato", nome_squadra=nome_squadra))

        
        squadra_proponente = scambio["squadra_proponente"]
        squadra_destinataria = scambio["squadra_destinataria"]
        crediti_offerti = scambio["crediti_offerti"] or 0
        crediti_richiesti = scambio["crediti_richiesti"] or 0
        giocatori_offerti = scambio["giocatori_offerti"] or []
        giocatori_richiesti = scambio["giocatori_richiesti"] or []

        
        # Eseguo il trasferimento dei giocatori
        # Posso modificare sia squadra_att che detentore cartellino perchè non possono essere proposti scambi per giocatori in prestito o in hold.
        for giocatore_id in giocatori_offerti:
            cur.execute('''
                        UPDATE giocatore
                        SET detentore_cartellino = %s,
                            squadra_att = %s
                        WHERE id = %s;
            ''', (squadra_destinataria, squadra_destinataria, giocatore_id))

            # Annullo gli altri scambi in cui il giocatore è coinvolto
            cur.execute('''
                        UPDATE scambio
                        SET stato = 'annullato'
                        WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (giocatore_id, giocatore_id, id))
            
        for giocatore_id in giocatori_richiesti:
            cur.execute('''
                        UPDATE giocatore
                        SET detentore_cartellino = %s,
                            squadra_att = %s
                        WHERE id = %s;
            ''', (squadra_proponente, squadra_proponente, giocatore_id))

            # Annullo gli altri scambi in cui il giocatore è coinvolto
            cur.execute('''
                        UPDATE scambio
                        SET stato = 'annullato'
                        WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (giocatore_id, giocatore_id, id))
        
        # Aggiorno i crediti delle due squadre
        cur.execute('''
                    UPDATE squadra
                    SET crediti = crediti - %s + %s
                    WHERE nome = %s;
        ''', (crediti_offerti, crediti_richiesti, squadra_proponente))
        
        cur.execute('''
                    UPDATE squadra
                    SET crediti = crediti - %s + %s
                    WHERE nome = %s;
        ''', (crediti_richiesti, crediti_offerti, squadra_destinataria))
        
        
        # Aggiorno lo stato dello scambio
        cur.execute('''
                    UPDATE scambio
                    SET stato = 'accettato',
                    data_risposta = NOW() AT TIME ZONE 'Europe/Rome'
                    WHERE id = %s;
        ''', (id,))
        
        # Attiva eventuali prestiti collegati allo scambio
        prestiti_collegati = []
        if scambio and scambio['prestito_associato']:
            cur.execute('''
                        SELECT id, giocatore, squadra_ricevente, squadra_prestante
                        FROM prestito
                        WHERE id = ANY(%s) AND stato = 'in_attesa';
            ''', (scambio['prestito_associato'],))
            prestiti_collegati = cur.fetchall()
        
        for prestito in prestiti_collegati:
            # Attiva il prestito (stato = 'in_corso' come in attiva_prestito)
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'in_corso'
                        WHERE id = %s;
            ''', (prestito['id'],))
            
            # Aggiorna il contratto del giocatore in prestito
            cur.execute('''
                        UPDATE giocatore
                        SET tipo_contratto = 'Fanta-Prestito',
                            squadra_att = %s
                        WHERE id = %s;
            ''', (prestito['squadra_ricevente'], prestito['giocatore']))
            
            # Rifiuta altri prestiti in attesa per lo stesso giocatore dalla stessa squadra prestante
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'rifiutato'
                        WHERE squadra_prestante = %s
                            AND giocatore = %s
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (prestito['squadra_prestante'], prestito['giocatore'], prestito['id']))
            
            # Annulla altri scambi che coinvolgono questo giocatore
            cur.execute('''
                        UPDATE scambio
                        SET stato = 'annullato'
                        WHERE (%s = ANY(giocatori_offerti) OR %s = ANY(giocatori_richiesti))
                            AND stato = 'in_attesa'
                            AND id <> %s;
            ''', (prestito['giocatore'], prestito['giocatore'], id))
        
        conn.commit()
        flash(f"✅ Scambio completato con successo tra {squadra_proponente} e {squadra_destinataria}", "success")
        telegram_utils.scambio_risposta(conn, id, "Accettato")
        return True
    
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"Errore durante l'esecuzione dello scambio: {e}")
        flash("❌ Errore nell'esecuzione dello scambio. Rivedere i valori dello scambio.", "danger")
        return False
    
    finally:
        cur.close()
        
        
        
        
        
def annulla_scambio(scambio_id, conn):
    
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Recupera gli ID dei prestiti associati prima di annullare lo scambio
        cur.execute('''
                    SELECT prestito_associato, stato
                    FROM scambio 
                    WHERE id = %s
                    FOR UPDATE;
        ''', (scambio_id,))
        scambio = cur.fetchone()
        
        # Controllo se lo scambio è ancora annullabile
        if not scambio or scambio['stato'] != 'in_attesa':
            conn.rollback()
            return
        
        # Aggiorno lo stato
        cur.execute('''
                    UPDATE scambio 
                    SET stato = 'annullato' 
                    WHERE id = %s;
        ''', (scambio_id,))
        
        # Annulla anche i prestiti collegati, se ce ne sono
        if scambio and scambio['prestito_associato']:
            cur.execute('''
                        UPDATE prestito
                        SET stato = 'annullato'
                        WHERE id = ANY(%s) AND stato = 'in_attesa';
            ''', (scambio['prestito_associato'],))
        
        conn.commit()
    
    except Exception as e:
        print(f"Errore durante l'annullamento dello scambio: {e}")
        conn.rollback()
        return False

    finally:
        cur.close()







def format_prestito(conn, lista_prestiti):
    if not lista_prestiti:
        return ""
    
    formatted_prestiti = []
    cur = None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        for prestito_id in lista_prestiti:
            cur.execute('''
                        SELECT g.nome, p.tipo_prestito, p.crediti_riscatto
                        FROM prestito p
                        JOIN giocatore g
                        ON p.giocatore = g.id
                        WHERE p.id = %s;
            ''', (prestito_id,))
            info_prestito = cur.fetchone()
            
            if info_prestito:
                giocatore = info_prestito['nome']
                tipo_prestito = info_prestito['tipo_prestito']
                crediti_riscatto = info_prestito['crediti_riscatto']
                
                tipo_map = {'secco': 'Secco', 'diritto_di_riscatto': 'DDR', 'obbligo_di_riscatto': 'ODR'}
                tipo_str = tipo_map.get(tipo_prestito, tipo_prestito)
                riscatto_str = f" (risc. {crediti_riscatto})" if crediti_riscatto and crediti_riscatto > 0 else ""
                
                prestito_str = f"• {giocatore} [Prestito {tipo_str}{riscatto_str}]"
                formatted_prestiti.append(prestito_str)
        
        return "\n".join(formatted_prestiti)
    
    except Exception as e:
        print(f"Errore in format_prestito: {e}")
        return ""
    
    finally:
        cur.close()
