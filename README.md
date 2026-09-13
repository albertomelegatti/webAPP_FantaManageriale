# Fanta Manageriale

Applicazione web per la gestione di una lega di fantacalcio "manageriale": un formato in cui le squadre non si ricostruiscono ogni anno, ma vivono in continuità stagione dopo stagione attraverso un mercato fatto di aste, scambi diretti tra squadre, prestiti con o senza diritto di riscatto, un draft per i giocatori U21 e un vincolo di bilancio espresso in crediti. L'app è il registro di tutto questo: chi possiede quale giocatore, con quale contratto, a quali condizioni, e l'interfaccia con cui le squadre propongono operazioni e l'amministratore della lega le arbitra.

È una Flask application servita da gunicorn, con Postgres (Supabase) come unica fonte di verità e Telegram come canale di notifica. Non c'è un frontend separato: le pagine sono renderizzate lato server con Jinja, e solo le viste con molte righe (il listone dei giocatori, il registro dei movimenti di mercato) disegnano la tabella nel browser a partire da un blocco dati compatto, per evitare di spedire centinaia di righe di HTML identico.

## Perché è fatta così

Il codice non è nato con questa struttura. È cresciuto per anni come un insieme di file piatti nella cartella principale — un `main.py` da settecento righe, un `user_mercato.py` da mille — dove ogni route mescolava instradamento HTTP, query SQL scritte a mano, regole di business e formattazione per il template nello stesso corpo di funzione. Funzionava, ma ogni modifica costava sempre di più: cambiare una regola di dominio significava trovarla ripetuta in tre punti diversi, e non esisteva un solo test a dire se una modifica aveva rotto qualcosa altrove.

La struttura attuale è il risultato di un refactoring a comportamento neutrale — nessuna funzionalità è cambiata nel passaggio, solo dove vive il codice e come è organizzato — guidato da un principio semplice: **ogni pezzo di codice ha un solo motivo per cambiare**. Una regola del gioco cambia? Si tocca un modulo in `domini/`. Cambia una query? Si tocca un `repository`. Cambia cosa vede l'utente? Si tocca un `blueprint` o un template. Prima queste tre cose erano la stessa riga di codice; ora sono tre file diversi, e questo non è burocrazia — è ciò che permette di cambiare una cosa senza doverle capire e verificare tutte e tre.

Il secondo principio, meno visibile ma altrettanto strutturale, riguarda le prestazioni: su questo database il costo di una query non dipende quasi per niente da quanto è complessa, ma da quanto costa il viaggio di rete verso il server Postgres — circa 35-40 millisecondi indipendentemente dal fatto che la query sia una `SELECT` su una riga o un `JOIN` con aggregazione. Questo capovolge l'intuizione comune: la leva di performance che conta davvero non è "scrivere query più furbe", è **ridurre il numero di viaggi**. Una pagina che faceva dieci interrogazioni separate e ne fa cinque è due volte più veloce a prescindere da quanto siano ottimizzate le singole query. Diverse parti di questa codebase (la dashboard, il mercato, il listone) sono state riscritte proprio per questo motivo, e chiunque aggiunga codice nuovo dovrebbe ragionare nello stesso modo: prima di ottimizzare una query, chiedersi se si può eliminare del tutto raggruppandola con un'altra.

## Mappa della codebase

```
wsgi.py                    punto di ingresso per gunicorn in produzione
app/
  __init__.py               application factory: create_app()
  core/                     infrastruttura, senza logica di gioco
  domini/                   regole del gioco come funzioni pure
  repositories/             accesso ai dati, un modulo per aggregato
  services/                 composizione: uniscono più repository per una vista
  schemas/                  validazione dei form in ingresso (pydantic)
  blueprints/               routing HTTP: instradamento, non logica
  telegram_utils.py         notifiche e registro pubblico dei movimenti
  templates/, static/       presentazione
CronJob/                    SQL eseguito direttamente su Postgres, fuori dall'app
tests/                      rete di sicurezza del refactoring
```

Le frecce vanno in un solo verso. `blueprints` chiama `services` e `repositories`; `services` chiama `repositories` e `domini`; `repositories` non chiama nessuno di questi, parla solo con Postgres attraverso un cursore che riceve dall'esterno; `domini` non chiama nulla, nemmeno un altro modulo applicativo. Se ti accorgi di voler importare `blueprints` dentro `repositories`, o `flask` dentro `domini`, non è un dettaglio stilistico da sistemare dopo: è il segnale che la responsabilità è nel posto sbagliato.

### `app/core/` — l'infrastruttura

Tutto ciò che l'applicazione usa ma che non sa nulla del fantacalcio: il pool di connessioni al database (`db.py`), la configurazione del logging (`logging.py`), la gerarchia delle eccezioni di dominio (`errori.py`), la formattazione di date e numeri per l'interfaccia (`tempo.py`, `formato.py`), la cache-busting degli asset statici (`asset.py`), il client per l'API esterna di Transfermarkt (`transfermarkt_api.py`).

**Perché esiste**: senza questo strato, ogni file che aveva bisogno di una connessione al database la apriva e chiudeva a modo suo — con la conseguenza, verificata più volte in produzione, che dimenticare un `finally` lasciava una connessione bloccata nel pool finché non si esauriva del tutto. `core/db.py` risolve il problema una volta sola, con due context manager:

```python
with connessione() as (conn, cur):
    ...          # letture, o scritture che il chiamante committerà a mano

with transazione() as (conn, cur):
    ...          # commit automatico in uscita pulita, rollback su eccezione
```

`connessione()` non committa mai da sola: chi la usa decide se e quando salvare. `transazione()` esiste per il caso comune in cui l'intero blocco è un'unica unità atomica. Le funzioni precedenti, `get_connection()`/`release_connection()`, restano nel modulo solo perché alcuni punti storici (in particolare `telegram_utils.py`, che gestisce le connessioni su un thread separato) le usano ancora: non vanno prese a modello per codice nuovo.

**Cosa non fa**: `core/` non contiene una sola riga che sappia cos'è un giocatore, uno scambio o un'asta. Se una funzione qui dentro ha bisogno di sapere che un'asta ha uno stato "in_corso", è nel posto sbagliato.

### `app/domini/` — le regole del gioco, come funzioni pure

`ruoli.py` (l'ordine dei ruoli Mantra e come normalizzarli), `calendario.py` (quali anni di scadenza sono proponibili per un prestito), `matching_transfermarkt.py` (come si riconosce che un giocatore del database e un profilo scaricato da Transfermarkt sono la stessa persona), `movimenti.py` (riconoscere quali squadre sono citate in un testo libero).

**Perché esiste**: sono le regole che *definiscono* il gioco, indipendenti da come i dati arrivano o da come vengono mostrati. Una funzione qui dentro riceve argomenti e restituisce un risultato — nessun accesso a database, nessuna richiesta di rete, nessuna dipendenza dall'ora corrente se non esplicitamente passata come parametro. Questo le rende testabili senza infrastruttura: un test su `ruolo_sort_key` non ha bisogno né di un database né di un server Flask in piedi, gira in millisecondi ed è quindi il tipo di test più economico ed esaustivo che la suite possa avere.

**Cosa non fa**: non legge né scrive nulla. Se una funzione "pura" ha bisogno di un cursore per completare il proprio lavoro, quella non è una funzione di dominio: è un repository, o la composizione tra un repository e una funzione di dominio che va scritta altrove (tipicamente in un service).

### `app/repositories/` — l'accesso ai dati

Un modulo per aggregato del dominio: `giocatori.py`, `squadre.py`, `aste.py`, `scambi.py`, `prestiti.py`, `draft.py`, `richieste.py`, `vetrina.py`, `configurazione.py`, `movimenti.py`, `albo_oro.py`, `stadio.py`, `autenticazione.py`, `transfermarkt.py`. Ogni funzione qui dentro esegue una o più query su una tabella o su un piccolo gruppo di tabelle strettamente collegate, e restituisce dati già nella forma che serve al chiamante — non righe grezze da rielaborare più in là.

**Perché esiste**: prima ogni blueprint scriveva il proprio SQL inline, il che significava che la stessa domanda ("quanti crediti ha questa squadra?") veniva posta al database con query leggermente diverse in punti diversi, e che cambiare una colonna richiedeva grep su tutto il progetto invece che aprire un file. Concentrare l'SQL qui rende ogni tabella un'unica superficie da conoscere.

Il modulo `repositories/__init__.py` fissa due regole che valgono per tutto il pacchetto, senza eccezioni:

1. **Un repository riceve un cursore, non lo crea.** Il chiamante possiede la connessione e decide i confini della transazione; il repository legge e scrive dentro quei confini, niente di più.
2. **Un repository non committa mai**, e non intercetta le proprie eccezioni. Solo chi ha aperto la transazione sa se l'operazione è completa; se qualcosa va storto, l'eccezione deve risalire perché chi la governa possa annullare tutto.

La ragione della seconda regola è concreta, non teorica: un vecchio bug in questa codebase faceva sì che una funzione di spostamento crediti committasse *la transazione del chiamante*, così che un'operazione a più passaggi (attivare un prestito: sposta crediti, poi aggiorna lo stato del prestito, poi aggiorna il giocatore) potesse fermarsi a metà lasciando i crediti già spostati ma il resto no. Un repository che non committa mai non può riprodurre quel bug per costruzione.

**Cosa non fa**: nessun repository importa Flask, né sa cosa sia una sessione HTTP, un form o un template. Un repository che ha bisogno di `flash()` o di `request` sta facendo il lavoro di un blueprint.

### `app/services/` — la composizione

`dashboard.py`, `mercato.py`, `rosa.py`, `listone.py`, `movimenti.py`, `chatbot.py`, `export_excel.py`. Un service esiste quando una vista ha bisogno di dati che arrivano da più repository e devono essere combinati, filtrati o aggregati prima di raggiungere il template — tipicamente per evitare che quella combinazione richieda una query per ogni riga di un elenco.

L'esempio più chiaro è `services/mercato.py`: la pagina degli scambi di una squadra mostra, per ogni proposta, i nomi dei giocatori coinvolti, la descrizione delle eventuali pick di draft e quella degli eventuali prestiti collegati. Risolvere ciascuno di questi per ogni riga, dentro il ciclo di rendering, costava 27 interrogazioni e 23 prelievi dal pool di connessioni per una pagina con 17 scambi — perché una delle funzioni coinvolte apriva una propria connessione invece di ricevere quella già aperta dalla route. Il service raccoglie tutti gli identificativi da tutte le righe prima del ciclo, li risolve in blocco con query fisse, e li ricompone dopo: il numero di interrogazioni non dipende più da quanti scambi ci sono.

**Cosa non fa**: un service non esegue mai `cur.execute(...)` direttamente su una tabella — quello è compito del repository che chiama. E non tutte le pagine hanno bisogno di un service: quando una route legge da un solo repository senza comporre nulla, chiamarlo direttamente dal blueprint è corretto, non una scorciatoia.

### `app/schemas/` — la validazione dei form

Oggi un solo modulo, `scambio.py`: modella con `pydantic` la proposta di scambio che arriva dal form di `nuovo_scambio`, un form con una trentina di campi opzionali (giocatori offerti/richiesti, crediti, pick di draft, prestiti con le loro condizioni). Prima questi campi venivano letti e validati a mano, uno per uno, dentro la route.

**Perché esiste**: uno schema dichiara *la forma* che i dati devono avere prima che qualunque logica di business li tocchi — un campo numerico vuoto vale zero, una lista di id deve contenere solo interi, un prestito "secco" non può avere un valore di riscatto. Non verifica la coerenza col resto del gioco (che le pick esistano davvero, che i crediti bastino): quello resta compito di repository e service, che hanno bisogno del database per saperlo.

### `app/blueprints/` — l'instradamento HTTP

Un blueprint per area funzionale: `public.py` (pagine pubbliche: home, listone, aste in sola lettura, movimenti, albo d'oro, health check), `auth.py` (login/logout/cambio password), `user.py` (la home della squadra dopo il login), `mercato.py`, `aste.py`, `prestiti.py`, `rosa.py`, `vetrina.py` (le aree operative di ciascuna squadra), `admin.py` (pannello di amministrazione della lega), `chat.py` (assistente sul regolamento), `webhook.py` (riceve eventi da Supabase), `jobs.py` (endpoint per uno scraping periodico, pensato per essere richiamato da un servizio esterno di uptime-monitoring al posto di un vero scheduler).

Il compito di una funzione-route, nella sua forma ideale, è breve: leggere cosa è arrivato dalla richiesta, aprire una connessione, chiamare un service o un repository, passare il risultato al template.

```python
@rosa_bp.route("/user_tagli/<nome_squadra>", methods=["GET", "POST"])
def user_tagli(nome_squadra):
    with connessione() as (conn, cur):
        ...
        rosa = servizio_rosa.giocatori_tagliabili(cur, nome_squadra)
    return render_template("user_tagli.html", ...)
```

Non tutte le route sono già arrivate a questa forma: alcune, soprattutto nel flusso di scambio e di gestione prestiti, contengono ancora logica di transizione di stato abbastanza corposa perché coinvolge più tabelle in sequenza dentro un'unica transazione. È debito riconosciuto, non un modello da imitare in codice nuovo: quando una route supera una manciata di righe di logica non banale, quella logica appartiene a un service.

**Cosa non fa**: un blueprint non scrive SQL. `public.py` conserva un'unica eccezione dichiarata (`SELECT 1;` sull'endpoint `/health`), e non è un'eccezione per pigrizia: è una sonda di connettività, categoria diversa da una query di dominio, e serve proprio perché la validazione delle connessioni nel pool è pigra e altrimenti quell'endpoint non proverebbe nulla.

**Sull'unica eccezione al nome in italiano**: il resto della codebase usa nomi di dominio in italiano (`squadra`, `giocatore`, `scambio`, `sposta_crediti`...). I nomi di blueprint che descrivono una *categoria architetturale* del modulo invece di un concetto di gioco restano in inglese — `admin.py`, `auth.py`, `public.py` — perché non sono vocabolario del fantacalcio, sono vocabolario dell'architettura web.

### `telegram_utils.py` — notifiche e registro pubblico

Un caso a parte, non ancora scomposto nei layer sopra perché la sua natura è ibrida: compone i testi delle notifiche Telegram (che richiedono di leggere lo stato di aste, scambi e prestiti dal database) e li invia attraverso una coda con un thread dedicato, per non far attendere la risposta HTTP al tempo di un'API esterna. La stessa funzione che invia al canale pubblico della lega (`send_message(nome_squadra='gruppo_comunicazioni', ...)`) scrive anche una riga nel registro dei movimenti di mercato — motivo per cui ogni punto che genera un evento pubblico dichiara esplicitamente quali squadre sono coinvolte, invece di lasciare che vengano dedotte in un secondo momento dal testo del messaggio.

### `CronJob/` — logica che vive nel database

Alcune transizioni di stato non hanno bisogno che l'applicazione sia in esecuzione per accadere: un'asta che chiude, un prestito che scade. Questi sono script SQL (`cron_job_aste.psql`, `cron_job_prestiti.sql`) pensati per girare come job schedulati direttamente su Postgres (`pg_cron`), indipendenti dal ciclo di vita di gunicorn. È un confine architetturale da tenere a mente: una parte, piccola ma reale, delle regole del gioco non passa mai da `app/`. Gli altri file in questa cartella sono migrazioni una tantum (nuove colonne, nuovi indici) da eseguire a mano, non job ricorrenti.

### `templates/` e `static/`

Jinja per il rendering server-side. Le tabelle con click-to-sort e i filtri lato client sono deliberati e vanno preservati quando si restila una pagina: sostituirli con un elenco di card toglierebbe una funzionalità, non solo uno stile. Le due pagine con centinaia di righe (`listone.html`, `movimenti_mercato.html`) non le disegna più il server: la route manda un unico blocco JSON compatto (i nomi dei campi una volta sola, poi una riga di valori per elemento) e uno script in `static/js/` costruisce le righe nel browser, venticinque alla volta, tenendo filtri e ordinamento istantanei perché operano sui dati già scaricati. Il componente di paginazione (`static/js/paginazione.js`) è condiviso fra le pagine che ne hanno bisogno: non va copiato, va riusato.

## Il percorso di una richiesta

Per capire come i layer collaborano davvero, segui una singola operazione dall'ingresso all'uscita: una squadra accetta una proposta di scambio.

1. Il browser invia un `POST` a `/mercato/mercato/<nome_squadra>` con il campo `accetta_scambio`.
2. Il blueprint `mercato.py` apre una connessione con `connessione(isolamento=REPEATABLE_READ)` — un isolamento più alto del default perché l'operazione deve vedere uno stato coerente di crediti e slot mentre decide se lo scambio è ancora eseguibile.
3. `controlla_scambio` blocca la riga dello scambio (`FOR UPDATE`, via `scambi_repo.per_id_bloccando`) e verifica, attraverso `squadre_repo` e `aste_repo`, che entrambe le squadre abbiano ancora crediti e slot sufficienti — condizioni che potrebbero essere cambiate da quando la proposta è stata creata.
4. Se tutto regge, `effettua_scambio` esegue in sequenza, sullo stesso cursore: il trasferimento dei giocatori (`giocatori_repo.trasferisci_cartellino`), l'annullamento di eventuali altre proposte concorrenti sugli stessi giocatori (`scambi_repo.annulla_concorrenti_per_giocatore`), il trasferimento delle pick coinvolte (`draft_repo.trasferisci`), il movimento dei crediti in entrambe le direzioni (`squadre_repo.scambia_crediti`), e l'eventuale attivazione dei prestiti collegati alla proposta.
5. Solo se ogni passaggio è andato a buon fine, il blueprint chiama `conn.commit()`. Se una qualunque delle chiamate solleva un'eccezione, nessun repository l'ha intercettata: risale fino al blueprint, che fa `rollback()` — nessuno dei passaggi precedenti sopravvive.
6. `telegram_utils.scambio_risposta` compone e accoda la notifica per entrambe le squadre e per il canale pubblico, dichiarando esplicitamente quali due squadre sono coinvolte per il registro dei movimenti.
7. Il blueprint fa redirect alla pagina del mercato, che a quel punto rilegge lo stato aggiornato.

Nota cosa *non* succede in questo percorso: il repository non decide mai se l'operazione è valida (quella è logica applicativa, nel blueprint), e il blueprint non scrive mai una riga di SQL (quello è compito del repository). Ogni passaggio ha un solo modulo responsabile, ed è per questo che l'intera operazione può essere ragionata un pezzo alla volta invece che come un blocco indivisibile di seicento righe.

## Regole che non vanno violate

Queste non sono preferenze di stile: ognuna esiste perché la sua violazione ha già causato un problema reale in questo progetto, prima che venisse fissata come regola.

**Un repository riceve un cursore e non committa mai.** È la regola con la storia più concreta (vedi sopra, sullo spostamento crediti) ed è quella su cui vale la pena essere più intransigenti in revisione: un `conn.commit()` dentro un file in `repositories/` è quasi sempre un errore, non una scelta.

**Le connessioni si prendono con `connessione()` o `transazione()`, mai con `get_connection()` nudo in codice nuovo.** Un `finally` dimenticato non solleva un errore visibile subito: il pool si esaurisce lentamente, e il sintomo compare come `WORKER TIMEOUT` in produzione molto dopo che il codice che lo ha causato è stato scritto.

**Un errore di dominio è un'eccezione, non un `flash()` seguito da un `return` silenzioso.** Le eccezioni in `core/errori.py` esistono perché intercettare un'eccezione imprevista, registrarla con un messaggio generico e restituire comunque una pagina con stato 200 ha nascosto in produzione un guasto reale del pool di connessioni per un'ora, servendo un listone vuoto senza che nulla lo segnalasse. L'error handler centralizzato in `create_app()` distingue le due categorie: un `ErroreDominio` diventa un messaggio comprensibile e un redirect; qualunque altra eccezione diventa una pagina di errore esplicita con stato 500 e uno stack trace nei log. Non intercettare un'eccezione imprevista dentro una route "per sicurezza": lasciarla risalire è la sicurezza.

**Il numero di interrogazioni verso il database è la prima cosa da ottimizzare, non l'ultima.** Prima di introdurre una query dentro un ciclo, chiedersi se gli identificativi necessari si possono raccogliere prima e risolvere in un'unica chiamata con `= ANY(%s)`. Un ciclo che fa una query per riga è quasi sempre un segnale che manca un repository con la funzione giusta, non che ne serve una nuova query più veloce.

**Il codice nuovo segue il vocabolario italiano già in uso**, con l'unica eccezione dei nomi che descrivono una categoria architetturale del modulo (non un concetto del gioco) — la stessa distinzione spiegata sopra per `blueprints/`. Non introdurre `SELECT *` in query nuove: le colonne omonime tra tabelle diverse in un `JOIN` sopravvivono per caso con `RealDictCursor` (vince l'ultima), ed è già successo che questo mascherasse un bug.

**Nessuna dipendenza nuova senza necessità reale.** Il progetto usa psycopg2 diretto, non un ORM: introdurre SQLAlchemy o un query builder non sarebbe un miglioramento, sarebbe una seconda strategia di accesso ai dati a convivere con la prima. Della documentazione risalente a un tentativo di introdurre SQLAlchemy che non è mai arrivato a compimento è stata rimossa proprio perché descriveva un'applicazione che non è mai esistita, e ha rischiato di trarre in inganno chi la leggeva credendo fosse ancora vera.

**La suite di test è la rete di sicurezza del refactoring, non un accessorio.** Il database di sviluppo è distinto da quello di produzione, ed è quello contro cui gira la suite: i test che scrivono (`test_scrittura_*.py`) usano un'isolazione a savepoint (`tests/isolamento.py`) che emula i confini di transazione reali senza lasciare nulla di permanente. Nessun test, per nessun motivo, deve scrivere sul database di produzione o inviare una notifica Telegram reale — entrambe le cose sono neutralizzate a livello di sessione in `conftest.py`, e vanno lasciate così.
