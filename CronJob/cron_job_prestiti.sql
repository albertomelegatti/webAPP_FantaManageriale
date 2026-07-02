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
      crediti = s.crediti - p.crediti_riscatto
  FROM prestito p
  WHERE p.squadra_ricevente = s.nome
    AND p.tipo_prestito = 'obbligo_di_riscatto'
    AND p.stato = 'riscattato'
    AND p.data_fine <= NOW() AT TIME ZONE 'Europe/Rome';

  UPDATE squadra s
  SET
      crediti = s.crediti + p.crediti_riscatto
  FROM prestito p
  WHERE p.squadra_prestante = s.nome
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

  UPDATE giocatore g
  SET 
      squadra_att = detentore_cartellino,
      tipo_contratto = 'Indeterminato'
  WHERE g.tipo_contratto = 'Prestito Reale'