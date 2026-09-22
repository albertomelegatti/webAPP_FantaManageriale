-- ============================================================================
-- Chiusura dei prestiti scaduti. Chiamata dal job pg_cron
-- "Elaborazione prestiti conclusi" (vedi cron_jobs.sql).
--
-- Il job gira alle 23:59 ora italiana e chiude i prestiti che scadono in
-- giornata. data_fine e' salvata come ora italiana "nominale" (il 01/07 alle
-- 23:59:59), quindi il confronto e' con la mezzanotte italiana di domani.
--
-- Un riscatto diventa effettivo solo qui, alla fine del prestito: fino ad
-- allora il giocatore resta un Fanta-Prestito e i crediti non si muovono.
--   * diritto di riscatto: solo se la squadra ricevente l'ha esercitato
--     (stato 'riscattato');
--   * obbligo di riscatto: sempre.
-- ============================================================================

CREATE OR REPLACE FUNCTION public.processa_prestiti_conclusi()
 RETURNS void
 LANGUAGE plpgsql
AS $function$
DECLARE
  v_limite timestamp := ((NOW() AT TIME ZONE 'Europe/Rome')::date + 1)::timestamp;
  r record;
BEGIN
  -- 1. Riscatti: il giocatore passa alla squadra ricevente, che paga il riscatto
  --    alla prestante. Un prestito alla volta, cosi' una squadra con piu'
  --    riscatti li paga tutti (un UPDATE ... FROM ne applicherebbe uno solo).
  FOR r IN
    SELECT id, giocatore, squadra_prestante, squadra_ricevente,
           COALESCE(crediti_riscatto, 0) AS crediti_riscatto
    FROM prestito
    WHERE data_fine < v_limite
      AND (   (tipo_prestito = 'diritto_di_riscatto' AND stato = 'riscattato')
           OR (tipo_prestito = 'obbligo_di_riscatto'
               AND stato IN ('in_corso', 'richiesta_di_terminazione', 'riscattato')))
    FOR UPDATE
  LOOP
    UPDATE squadra SET crediti = crediti - r.crediti_riscatto WHERE nome = r.squadra_ricevente;
    UPDATE squadra SET crediti = crediti + r.crediti_riscatto WHERE nome = r.squadra_prestante;

    UPDATE giocatore
    SET squadra_att = r.squadra_ricevente,
        detentore_cartellino = r.squadra_ricevente,
        tipo_contratto = 'Indeterminato'
    WHERE id = r.giocatore;

    DELETE FROM vetrina WHERE id_giocatore = r.giocatore;

    UPDATE prestito SET stato = 'terminato', richiedente_terminazione = NULL WHERE id = r.id;
  END LOOP;

  -- 2. Prestiti secchi e diritti di riscatto non esercitati: il giocatore torna
  --    alla squadra prestante. Anche quelli con una richiesta di terminazione
  --    anticipata rimasta in sospeso fino alla scadenza.
  UPDATE giocatore g
  SET squadra_att = p.squadra_prestante,
      tipo_contratto = 'Indeterminato'
  FROM prestito p
  WHERE g.id = p.giocatore
    AND p.tipo_prestito IN ('secco', 'diritto_di_riscatto')
    AND p.stato IN ('in_corso', 'richiesta_di_terminazione')
    AND p.data_fine < v_limite;

  UPDATE prestito
  SET stato = 'terminato',
      richiedente_terminazione = NULL
  WHERE tipo_prestito IN ('secco', 'diritto_di_riscatto')
    AND stato IN ('in_corso', 'richiesta_di_terminazione')
    AND data_fine < v_limite;
END;
$function$;
