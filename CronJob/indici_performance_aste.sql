-- Indici per le query sul modulo aste/rilanci (asta.partecipanti, asta.stato, asta.tempo_fine_*).
-- Oggi la tabella `asta` ha poche decine di righe quindi tutte le query fanno seq scan
-- in ~1ms, ma senza questi indici il costo cresce linearmente ad ogni stagione (nessun
-- archiving delle aste concluse). Eseguire una tantum sul DB (es. Supabase SQL editor).
--
-- La connessione usata da Claude Code verso questo DB è in sola lettura, quindi questo
-- script va lanciato manualmente.

-- Query con `nome_squadra = ANY(partecipanti)` (queries.py:get_slot_aste, user_aste.py listing,
-- user_mercato.py) richiedono un indice GIN: un btree normale non copre la ricerca in array.
CREATE INDEX IF NOT EXISTS idx_asta_partecipanti_gin
    ON asta USING GIN (partecipanti);

-- Copre il cron job (CronJob/cron_job_aste.psql) che filtra per stato + tempo_fine_asta
-- per chiudere le aste scadute.
CREATE INDEX IF NOT EXISTS idx_asta_stato_tempo_fine_asta
    ON asta (stato, tempo_fine_asta);

-- Copre il cron job per la fase 'mostra_interesse' -> 'in_corso'/'conclusa'.
CREATE INDEX IF NOT EXISTS idx_asta_stato_tempo_fine_interesse
    ON asta (stato, tempo_fine_mostra_interesse);

-- Copre get_offerta_totale (squadra_vincente + stato = 'in_corso') e il ramo
-- "stato = 'conclusa' AND squadra_vincente = ..." del listing in user_aste.py.
CREATE INDEX IF NOT EXISTS idx_asta_squadra_vincente_stato
    ON asta (squadra_vincente, stato);
