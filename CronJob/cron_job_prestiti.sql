-- Cron job per la gestione della fine dei prestiti

-- 1. Aggiorna i giocatori il cui prestito è scaduto
-- Riporta il giocatore alla squadra di origine e imposta il contratto a Indeterminato
UPDATE giocatore g
SET 
    g.squadra_att = p.squadra_prestante,
    g.tipo_contratto = 'Indeterminato'
FROM prestito p
WHERE g.id = p.giocatore
  AND p.stato = 'in_corso'
  AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';
  

-- 2. Aggiorna lo stato dei prestiti scaduti
-- Imposta lo stato del prestito a 'concluso'
UPDATE prestito
SET stato = 'terminato'
WHERE stato = 'in_corso'
  AND data_fine <= NOW() AT TIME ZONE 'Europe/Rome';
