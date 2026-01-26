-- da verificare come incide il cambiare lo stato del prestito + per obbligo di riscatto bisogna anche passare i crediti

-- Cron job per la gestione della fine dei prestiti

-- 1. Tipo prestito = SECCO
-- Riporta il giocatore alla squadra di origine e imposta il contratto a Indeterminato
UPDATE giocatore g
SET 
    g.squadra_att = p.squadra_prestante,
    g.tipo_contratto = 'Indeterminato'
FROM prestito p
WHERE g.id = p.giocatore
  AND p.stato = 'in_corso'
  AND p.tipo_prestito = 'secco'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';


-- 2. Aggiorna lo stato dei prestiti scaduti
-- Imposta lo stato del prestito a 'concluso'
UPDATE prestito
SET stato = 'terminato'
WHERE stato = 'in_corso'
  AND data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

-- 3. Tipo prestito = DIRITTO DI RISCATTO
-- Gestione dei prestiti con diritto di riscatto che vengono riscattati
UPDATE giocatore g
SET
    g.squadra_att = p.squadra_prestante,
    g.tipo_contratto = 'Indeterminato'
FROM prestito p
WHERE p.giocatore = g.id
  AND p.tipo_prestito = 'diritto_di_riscatto'
  AND p.stato = 'in_corso'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';



-- 4. Tipo prestito = OBBLIGO DI RISCATTO
UPDATE giocatore g
SET
    g.squadra_att = p.squadra_ricevente,
    g.tipo_contratto = 'Indeterminato',
    p.stato = 'riscattato'
FROM prestito p
WHERE p.giocatore = g.id
  AND p.tipo_prestito = 'obbligo_di_riscatto'
  AND p.stato = 'in_corso'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

