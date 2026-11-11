-- ============================================================================
-- Draft U21 live: stato del draft di un anno e tracciamento delle scelte.
-- Script unico, idempotente, in una transazione sola (es. Supabase SQL editor).
--
-- La connessione usata da Claude Code verso questo DB e' in sola lettura per le
-- modifiche allo schema: questo script va lanciato a mano, prima su dev e poi
-- su prod. Le colonne nuove hanno un default, quindi le pagine attuali e lo
-- script scripts/draft_u21/assegna.py continuano a funzionare anche prima che
-- il codice del draft live sia in produzione.
--
-- Prima di lanciarlo, verificare che non ci siano pick con lo stesso numero
-- nello stesso anno (l'indice unico qui sotto fallirebbe, e la transazione
-- si annullerebbe per intero):
--
--   SELECT anno, numero, count(*) FROM draft
--   WHERE numero IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1;
--
-- (verificato su dev: nessuna riga)
-- ============================================================================

BEGIN;

-- 1. Lo stato del draft di un anno: preparato (ordine generato, non ancora
--    aperto), aperto (le squadre scelgono), chiuso. La pick "in corso" non e'
--    salvata qui: la ricava la query, e' la pick con `numero` piu' basso non
--    ancora usata ne' saltata. Un puntatore a parte potrebbe andare fuori
--    sincrono con la tabella draft.
--    `anno` e' uno smallint, mentre draft.anno e' una date (1 gennaio): il
--    collegamento passa da EXTRACT(YEAR FROM draft.anno).
CREATE TABLE IF NOT EXISTS draft_sessione (
    anno               smallint PRIMARY KEY,
    stato              varchar NOT NULL DEFAULT 'preparato'
                       CHECK (stato IN ('preparato', 'aperto', 'chiuso')),
    ordine_generato_il timestamptz,
    aperto_il          timestamptz,
    chiuso_il          timestamptz
);

-- Al massimo un draft aperto alla volta.
CREATE UNIQUE INDEX IF NOT EXISTS ux_draft_sessione_aperto
    ON draft_sessione ((true)) WHERE stato = 'aperto';

-- 2. Le scelte. `saltata`: la pick e' persa (slot Primavera pieni) o saltata
--    dall'admin; senza questo segno sembrerebbe ancora da fare e bloccherebbe
--    il draft. `scelta_il` / `scelta_da`: quando e da chi (la squadra, o
--    l'admin che sceglie per un assente).
ALTER TABLE draft ADD COLUMN IF NOT EXISTS saltata   boolean NOT NULL DEFAULT false;
ALTER TABLE draft ADD COLUMN IF NOT EXISTS scelta_il timestamptz;
ALTER TABLE draft ADD COLUMN IF NOT EXISTS scelta_da varchar;

-- Una pick saltata non ha un giocatore.
ALTER TABLE draft DROP CONSTRAINT IF EXISTS ck_draft_saltata_senza_giocatore;
ALTER TABLE draft ADD CONSTRAINT ck_draft_saltata_senza_giocatore
    CHECK (NOT (saltata AND id_giocatore_scelto IS NOT NULL));

-- 3. Una sola pick per numero dentro lo stesso anno: impedisce di generare
--    l'ordine due volte. Parziale, perche' le pick degli anni futuri hanno
--    numero NULL finche' l'ordine non viene generato.
CREATE UNIQUE INDEX IF NOT EXISTS ux_draft_anno_numero
    ON draft (anno, numero) WHERE numero IS NOT NULL;

COMMIT;
