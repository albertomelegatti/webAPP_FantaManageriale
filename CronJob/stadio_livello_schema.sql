-- Rendita annuale per livello di stadio, modificabile dall'admin (pagina Stadi).
-- Prima era la costante RENDITA_STADIO in app/services/crediti_stadi_slot.py,
-- copiata dalla tabella della sezione 4 del regolamento.
--
-- La connessione usata da Claude Code verso questo DB e' in sola lettura per le
-- modifiche allo schema: questo script va lanciato a mano, prima su dev e poi
-- su prod. E' idempotente (si puo' rilanciare) e non sovrascrive valori gia'
-- modificati. Finche' la tabella non esiste l'app usa i valori di default del
-- codice e la pagina admin avvisa che le rendite non sono ancora modificabili.
--
-- Nessun BEGIN/COMMIT: i test lo eseguono dentro una transazione che poi annullano.

CREATE TABLE IF NOT EXISTS stadio_livello (
    livello smallint PRIMARY KEY CHECK (livello >= 0),
    rendita integer  NOT NULL CHECK (rendita >= 0)
);

INSERT INTO stadio_livello (livello, rendita) VALUES
    (0, 0), (1, 4), (2, 8), (3, 14), (4, 18), (5, 25), (6, 30), (7, 39), (8, 44)
ON CONFLICT (livello) DO NOTHING;
