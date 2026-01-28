-- Cron job per la gestione della fine dei prestiti

-- 1. Tipo prestito = SECCO
-- Riporta il giocatore alla squadra di origine e imposta il contratto a Indeterminato
UPDATE giocatore g
SET 
    squadra_att = p.squadra_prestante,
    tipo_contratto = 'Indeterminato'
FROM prestito p
WHERE g.id = p.giocatore
  AND p.stato = 'in_corso'
  AND p.tipo_prestito = 'secco'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

UPDATE prestito
SET stato = 'terminato'
WHERE stato = 'in_corso'
  AND tipo_prestito = 'secco'
  AND data_fine <= NOW() AT TIME ZONE 'Europe/Rome';


-- 2. Tipo prestito = DIRITTO DI RISCATTO
-- Gestione dei prestiti con diritto di riscatto che non vengono riscattati
UPDATE giocatore g
SET
    squadra_att = p.squadra_prestante,
    tipo_contratto = 'Indeterminato'
FROM prestito p
WHERE p.giocatore = g.id
  AND p.tipo_prestito = 'diritto_di_riscatto'
  AND p.stato = 'in_corso'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

UPDATE prestito
SET stato = 'terminato'
WHERE tipo_prestito = 'diritto_di_riscatto'
  AND stato = 'in_corso'
  AND data_fine <= NOW() AT TIME ZONE 'Europe/Rome';



-- 3.1 Tipo prestito = OBBLIGO DI RISCATTO
UPDATE giocatore g
SET
    squadra_att = p.squadra_ricevente,
    tipo_contratto = 'Indeterminato'
FROM prestito p
WHERE p.giocatore = g.id
  AND p.tipo_prestito = 'obbligo_di_riscatto'
  AND p.stato = 'in_corso'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

UPDATE prestito
SET stato = 'riscattato'
WHERE tipo_prestito = 'obbligo_di_riscatto'
  AND stato = 'in_corso'
  AND data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

-- 3.2 Aggiornamento crediti per obbligo di riscatto
UPDATE squadra s
SET
    s.crediti = s.crediti - p.costo_riscatto
FROM prestito p
WHERE p.squadra_ricevente = s.nome_squadra
  AND p.tipo_prestito = 'obbligo_di_riscatto'
  AND p.stato = 'riscattato'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

UPDATE squadra s
SET
    s.crediti = s.crediti + p.costo_riscatto
FROM prestito p
WHERE p.squadra_prestante = s.nome_squadra
  AND p.tipo_prestito = 'obbligo_di_riscatto'
  AND p.stato = 'riscattato'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

-- 3.3 Impostazione stato prestito a terminato per obbligo di riscatto dopo aver aggiornato i crediti
UPDATE prestito
SET
    stato = 'terminato'
WHERE tipo_prestito = 'obbligo_di_riscatto'
  AND stato = 'riscattato'
  AND data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

