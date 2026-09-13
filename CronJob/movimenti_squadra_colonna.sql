-- ============================================================================
-- movimenti_squadra: colonna `squadre` al posto del filtro ILIKE su testo
-- libero. Script unico, idempotente.
--
-- Oggi il legame fra un movimento e le squadre coinvolte non è registrato in
-- una colonna: `movimenti_repo.per_squadra` cerca il nome della squadra come
-- sottostringa del testo dell'evento (`evento ILIKE '%nome%'`). Due conseguenze
-- note: non è indicizzabile, e due squadre con un nome una sottostringa
-- dell'altra si mescolerebbero (verificato che oggi non è il caso, ma nulla
-- lo garantisce in futuro).
--
-- Uno scambio coinvolge sempre due squadre (verificato sui dati), quindi la
-- colonna è un array, come già `asta.partecipanti`.
--
-- La connessione usata da Claude Code verso questo DB è in sola lettura per le
-- DML che alterano dati esistenti: questo script va lanciato a mano (es.
-- Supabase SQL editor) o dall'assistente con conferma esplicita.
-- ============================================================================

-- 1. La colonna, vuota per le righe nuove finché il codice applicativo non la
--    popola esplicitamente (vedi app/telegram_utils.py, salva_movimento).
ALTER TABLE movimenti_squadra ADD COLUMN IF NOT EXISTS squadre text[];

-- 2. Backfill delle righe esistenti: stessa euristica per sottostringa che
--    usava finora la query di lettura, applicata una volta sola. La sua
--    accuratezza sui dati storici è quindi identica a quella di oggi, non
--    peggiore — e da qui in avanti ogni riga nuova arriva con le squadre
--    dichiarate esplicitamente dal chiamante, non dedotte dal testo.
UPDATE movimenti_squadra m
SET squadre = COALESCE((
    SELECT array_agg(s.nome ORDER BY s.nome)
    FROM squadra s
    WHERE s.nome <> 'Svincolato' AND m.evento ILIKE '%' || s.nome || '%'
), ARRAY[]::text[])
WHERE squadre IS NULL;

-- 3. GIN: `squadre @> ARRAY[%s]` sostituisce l'ILIKE non indicizzabile.
CREATE INDEX IF NOT EXISTS idx_movimenti_squadra_squadre_gin ON movimenti_squadra USING GIN (squadre);
