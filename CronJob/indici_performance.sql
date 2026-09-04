-- ============================================================================
-- Indici di performance — script unico, idempotente.
-- Sostituisce e assorbe indici_performance_aste.sql (che risultava scritto ma
-- mai eseguito: prima di questo file il database aveva SOLO le primary key e
-- qualche vincolo UNIQUE, nessun indice su colonne di filtro).
--
-- La connessione usata da Claude Code verso questo DB è in sola lettura, quindi
-- lo script va lanciato a mano (es. Supabase SQL editor). È idempotente:
-- rieseguirlo non fa danni.
--
-- Ogni CREATE INDEX è preceduto dalla ragione e, dove misurata, dalla situazione
-- attuale. Le misure sono da EXPLAIN ANALYZE sul DB di sviluppo (1.056 giocatori,
-- 990 pick di draft, 627 movimenti, 75 aste), settembre 2026.
--
-- Nota onesta sull'aspettativa: a questi volumi tutte le query girano già sotto
-- i 2 ms, quindi il guadagno immediato è piccolo. Il punto di questi indici è che
-- il costo attuale cresce *linearmente* con i dati e le tabelle non vengono mai
-- archiviate a fine stagione: senza indici, ogni stagione aggiunge un po' di
-- lavoro a ogni singola pagina.
-- ============================================================================


-- ---------------------------------------------------------------------------
-- giocatore — la tabella più interrogata dell'app
-- ---------------------------------------------------------------------------

-- Filtro presente in quasi ogni pagina: conteggio slot, rosa, primavera,
-- prestiti in, elenco giocatori per lo scambio.
-- Misurato: `WHERE squadra_att = 'Diablitos FC' AND tipo_contratto IN (...)`
-- fa un seq scan di 1.056 righe per restituirne 27 (0,23 ms).
CREATE INDEX IF NOT EXISTS idx_giocatore_squadra_att_contratto
    ON giocatore (squadra_att, tipo_contratto);

-- Usato dalle pagine vetrina, tagli e prestiti out, che filtrano sul detentore
-- del cartellino invece che sulla squadra attuale.
CREATE INDEX IF NOT EXISTS idx_giocatore_detentore_cartellino
    ON giocatore (detentore_cartellino);

-- Il job Transfermarkt cerca i giocatori già abbinati per aggiornarne data di
-- nascita e scadenza contratto.
CREATE INDEX IF NOT EXISTS idx_giocatore_id_transfermarkt
    ON giocatore (id_transfermarkt)
    WHERE id_transfermarkt IS NOT NULL;

-- NOTA — deliberatamente NON creato: un indice su `priorita = 1`.
-- Oggi 534 righe su 1.056 hanno priorita = 1, cioè il 50% della tabella: il
-- planner ignorerebbe l'indice e sceglierebbe comunque il seq scan. Ha senso
-- solo se un domani i giocatori a priorita <> 1 diventassero la larga maggioranza.


-- ---------------------------------------------------------------------------
-- asta — cresce ogni stagione senza mai essere archiviata
-- ---------------------------------------------------------------------------

-- `%s = ANY(partecipanti)` (queries.get_slot_aste, elenco aste utente,
-- aggregazione slot in user_mercato) richiede un GIN: un btree non copre
-- la ricerca dentro un array.
CREATE INDEX IF NOT EXISTS idx_asta_partecipanti_gin
    ON asta USING GIN (partecipanti);

-- Copre il cron job che chiude le aste scadute (CronJob/cron_job_aste.psql).
CREATE INDEX IF NOT EXISTS idx_asta_stato_tempo_fine_asta
    ON asta (stato, tempo_fine_asta);

-- Copre la transizione 'mostra_interesse' -> 'in_corso'/'conclusa' dello stesso cron.
CREATE INDEX IF NOT EXISTS idx_asta_stato_tempo_fine_interesse
    ON asta (stato, tempo_fine_mostra_interesse);

-- Copre get_offerta_totale (squadra_vincente + stato = 'in_corso') e il ramo
-- "stato = 'conclusa' AND squadra_vincente = ..." dell'elenco aste utente.
CREATE INDEX IF NOT EXISTS idx_asta_squadra_vincente_stato
    ON asta (squadra_vincente, stato);

-- Chiave esterna verso giocatore, usata in ogni JOIN dell'elenco aste.
CREATE INDEX IF NOT EXISTS idx_asta_giocatore
    ON asta (giocatore);


-- ---------------------------------------------------------------------------
-- prestito
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_prestito_ricevente_stato
    ON prestito (squadra_ricevente, stato);

CREATE INDEX IF NOT EXISTS idx_prestito_prestante_stato
    ON prestito (squadra_prestante, stato);

-- Chiave esterna verso giocatore: JOIN in ogni pagina prestiti, più i controlli
-- "esiste già un prestito in attesa per questo giocatore".
CREATE INDEX IF NOT EXISTS idx_prestito_giocatore
    ON prestito (giocatore);

-- Il cron dei prestiti (CronJob/cron_job_prestiti.sql) filtra per tipo + stato +
-- data di scadenza su ognuno dei tre rami (secco, diritto, obbligo).
CREATE INDEX IF NOT EXISTS idx_prestito_tipo_stato_data_fine
    ON prestito (tipo_prestito, stato, data_fine);


-- ---------------------------------------------------------------------------
-- scambio
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_scambio_proponente_stato
    ON scambio (squadra_proponente, stato);

CREATE INDEX IF NOT EXISTS idx_scambio_destinataria_stato
    ON scambio (squadra_destinataria, stato);

-- L'accettazione di uno scambio annulla gli altri scambi in attesa che
-- coinvolgono gli stessi giocatori, con `id = ANY(giocatori_offerti)`:
-- di nuovo una ricerca dentro un array, che serve GIN.
CREATE INDEX IF NOT EXISTS idx_scambio_giocatori_offerti_gin
    ON scambio USING GIN (giocatori_offerti);

CREATE INDEX IF NOT EXISTS idx_scambio_giocatori_richiesti_gin
    ON scambio USING GIN (giocatori_richiesti);


-- ---------------------------------------------------------------------------
-- draft, richieste, vetrina
-- ---------------------------------------------------------------------------

-- 990 righe, filtrate per detentore in dashboard e pagina nuovo scambio.
CREATE INDEX IF NOT EXISTS idx_draft_detentore_att
    ON draft (detentore_att);

-- La pagina nuovo scambio elenca solo le pick non ancora usate.
CREATE INDEX IF NOT EXISTS idx_draft_pick_libere
    ON draft (detentore_att)
    WHERE id_giocatore_scelto IS NULL;

-- Chiude la N+1 di user_rosa (`esiste_gia_una_richiesta` chiamata una volta per
-- giocatore): dopo il refactoring diventerà una sola query con `= ANY(...)`,
-- ma l'indice serve in entrambi i casi.
CREATE INDEX IF NOT EXISTS idx_rmc_giocatore_stato
    ON richiesta_modifica_contratto (giocatore, stato);

-- Elenco admin delle richieste, ordinato per data decrescente.
CREATE INDEX IF NOT EXISTS idx_rmc_data
    ON richiesta_modifica_contratto (data DESC);


-- ---------------------------------------------------------------------------
-- movimenti_squadra — la query più lenta misurata
-- ---------------------------------------------------------------------------

-- Misurato: la dashboard di una squadra fa
--   WHERE evento ILIKE '%<nome squadra>%' AND evento NOT ILIKE '%🏷️ ASTA%'
--   ORDER BY data DESC
-- che costa 1,63 ms scandendo 627 righe per restituirne 69. È la query più
-- costosa fra quelle misurate, e gira a ogni apertura della dashboard.
--
-- Questo indice copre solo l'ORDER BY. Il filtro ILIKE su testo libero resta
-- non indicizzabile così com'è: la soluzione vera è una colonna `squadra`
-- esplicita popolata alla scrittura del movimento (Fase 9 del piano di
-- refactoring), che eliminerebbe anche il rischio che il nome di una squadra
-- sia sottostringa di un'altra e i movimenti si mescolino.
CREATE INDEX IF NOT EXISTS idx_movimenti_squadra_data
    ON movimenti_squadra (data DESC);


-- ---------------------------------------------------------------------------
-- Verifica dopo l'esecuzione
-- ---------------------------------------------------------------------------
-- Elenco degli indici creati:
--   SELECT tablename, indexname FROM pg_indexes
--   WHERE schemaname = 'public' AND indexname LIKE 'idx_%'
--   ORDER BY tablename, indexname;
--
-- Aggiornare le statistiche del planner subito dopo, altrimenti i nuovi indici
-- potrebbero non venire scelti finché non scatta l'autovacuum:
--   ANALYZE giocatore, asta, prestito, scambio, draft,
--           richiesta_modifica_contratto, movimenti_squadra;
--
-- Indici mai usati, da rivalutare dopo qualche settimana di esercizio:
--   SELECT relname, indexrelname, idx_scan FROM pg_stat_user_indexes
--   WHERE schemaname = 'public' AND idx_scan = 0 ORDER BY relname;
