-- ============================================================================
-- Elaborazione delle aste concluse. Chiamata ogni minuto dal job pg_cron
-- "Elaborazione aste concluse" (vedi cron_jobs.sql). Allineata a prod.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.processa_aste_concluse()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
BEGIN
    -- 1. Assegna i giocatori alla squadra vincente
    UPDATE giocatore g
    SET squadra_att = a.squadra_vincente,
        detentore_cartellino = a.squadra_vincente,
        tipo_contratto = 'Indeterminato',
        costo = a.ultima_offerta
    FROM asta a
    WHERE g.id = a.giocatore
      AND a.stato = 'conclusa'
      AND a.gia_elaborata = FALSE;

    -- 2. Scala i crediti della squadra vincente
    UPDATE squadra s
    SET crediti = crediti - a.ultima_offerta
    FROM asta a
    WHERE s.nome = a.squadra_vincente
      AND a.stato = 'conclusa'
      AND a.gia_elaborata = FALSE;

    -- 3. Segna l'asta come elaborata
    UPDATE asta
    SET gia_elaborata = TRUE
    WHERE stato = 'conclusa'
      AND gia_elaborata = FALSE;
END;
$function$;
