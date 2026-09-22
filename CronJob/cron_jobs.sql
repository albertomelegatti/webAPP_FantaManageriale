-- ============================================================================
-- Job pg_cron di prod, allineati a cron.job (progetto vhowswomnwhbfdpslsep).
--
-- cron.schedule con un nome gia' esistente aggiorna il job invece di crearne un
-- altro, quindi lo script si puo' rilanciare. Va eseguito da utente postgres:
-- cron.job mostra a ogni utente solo i propri job.
--
-- Gli orari sono in UTC (cron.timezone = GMT su Supabase).
--
-- Le funzioni richiamate stanno in file a parte:
--   processa_aste_concluse()     -> processa_aste_concluse.sql
--   processa_prestiti_conclusi() -> cron_job_prestiti.sql
-- ============================================================================


-- Ogni minuto: avanza lo stato delle aste.
SELECT cron.schedule('Aggiornamento aste', '* * * * *', $$
    -- 1. Da 'mostra_interesse' a 'in_corso' con almeno 2 iscritti
    UPDATE asta
    SET stato = 'in_corso',
        squadra_vincente = partecipanti[1],
        ultima_offerta = 1,
        tempo_fine_asta = NOW() AT TIME ZONE 'Europe/Rome' + INTERVAL '1 day',
        tempo_fine_mostra_interesse = NULL
    WHERE stato = 'mostra_interesse'
        AND tempo_fine_mostra_interesse <= NOW() AT TIME ZONE 'Europe/Rome'
        AND cardinality(partecipanti) >= 2;

    -- 2. Da 'mostra_interesse' a 'conclusa' con un solo iscritto
    UPDATE asta
    SET stato = 'conclusa',
        squadra_vincente = partecipanti[1],
        tempo_fine_asta = NOW() AT TIME ZONE 'Europe/Rome',
        tempo_fine_mostra_interesse = NULL,
        ultima_offerta = 1
    WHERE stato = 'mostra_interesse'
        AND tempo_fine_mostra_interesse < NOW() AT TIME ZONE 'Europe/Rome'
        AND cardinality(partecipanti) = 1;

    -- 3. Da 'in_corso' a 'conclusa'
    UPDATE asta
    SET stato = 'conclusa',
        gia_elaborata = FALSE,
        tempo_fine_asta = NOW() AT TIME ZONE 'Europe/Rome'
    WHERE (stato = 'in_corso'
        AND tempo_fine_asta <= NOW() AT TIME ZONE 'Europe/Rome')
        OR (stato = 'in_corso'
        AND cardinality(partecipanti) = 1);
$$);


-- Ogni minuto: assegna i giocatori delle aste concluse e scala i crediti.
SELECT cron.schedule('Elaborazione aste concluse', '* * * * *',
    $$SELECT public.processa_aste_concluse()$$);


-- Ogni ora: ordina gli iscritti delle aste in 'mostra_interesse', lasciando
-- fermo il primo (chi ha aperto l'asta).
SELECT cron.schedule('Ordina iscritti all''asta', '0 * * * *', $$
    UPDATE asta
    SET partecipanti = ARRAY[partecipanti[1]] || (
        SELECT array_agg(elem ORDER BY elem)
        FROM unnest(partecipanti[2:]) AS elem
    )
    WHERE array_length(partecipanti, 1) > 1
        AND stato = 'mostra_interesse';
$$);


-- Ogni giorno a mezzanotte UTC: tiene solo l'ultimo giorno di log dei job.
SELECT cron.schedule('Elimina log', '0 0 * * *', $$
    DELETE FROM cron.job_run_details
    WHERE end_time < now() - interval '1 days';
$$);


-- Ogni giorno alle 21:59 UTC, cioe' le 23:59 italiane con l'ora legale (in
-- vigore il 01/07, quando scadono i prestiti); con l'ora solare sono le 22:59,
-- sempre in giornata. Chiude i prestiti che scadono in giornata.
SELECT cron.schedule('Elaborazione prestiti conclusi', '59 21 * * *',
    $$SELECT public.processa_prestiti_conclusi()$$);
