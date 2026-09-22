-- ============================================================================
-- Riscatto effettivo a fine prestito: passi da lanciare a mano su prod
-- (Supabase SQL editor o pgAdmin), dopo cron_job_prestiti.sql.
-- ============================================================================

-- 1. Il job gira alle 23:59 ora italiana. pg_cron su Supabase ragiona in UTC
--    (cron.timezone = GMT): 21:59 UTC sono le 23:59 con l'ora legale, in vigore
--    il 01/07. Con l'ora solare il job gira alle 22:59, sempre in giornata.
SELECT cron.alter_job(
    (SELECT jobid FROM cron.job WHERE jobname = 'Elaborazione prestiti conclusi'),
    schedule := '59 21 * * *');

-- 2. Prestito 10 (Sabelli, Diaolo Porco -> Sborada): scaduto il 02/07/2026 con
--    una richiesta di terminazione mai gestita, che la vecchia funzione non
--    considerava. Il giocatore e' gia' tornato a Diaolo Porco: resta solo da
--    chiudere il prestito.
UPDATE prestito
SET stato = 'terminato', richiedente_terminazione = NULL
WHERE id = 10 AND stato = 'richiesta_di_terminazione';
