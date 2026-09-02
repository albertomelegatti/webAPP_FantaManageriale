-- Schema per l'abbinamento dei giocatori con Transfermarkt (data di nascita,
-- scadenza contratto reale). Eseguire una tantum sul DB (es. Supabase SQL editor).
--
-- La connessione usata da Claude Code verso questo DB è in sola lettura, quindi questo
-- script va lanciato manualmente.

ALTER TABLE giocatore
    ADD COLUMN IF NOT EXISTS id_transfermarkt integer,
    ADD COLUMN IF NOT EXISTS data_nascita date,
    ADD COLUMN IF NOT EXISTS scadenza_contratto date;

-- Mappa club fantacalcio (giocatore.club) -> nome ufficiale su Transfermarkt, usata da
-- scripts/match_transfermarkt.py per sapere quale club scaricato corrisponde a quale
-- nostro club. Verificata scaricando `tfmkt clubs -s 2026` (i 20 club che compaiono
-- oggi in `SELECT DISTINCT club FROM giocatore WHERE priorita = 1`, stagione 2026/27).
-- Editabile direttamente qui via SQL se un nome cambia o un club viene promosso/retrocesso.
CREATE TABLE IF NOT EXISTS transfermarkt_mappa_club (
    club varchar PRIMARY KEY,
    nome_transfermarkt varchar NOT NULL
);
COMMENT ON TABLE transfermarkt_mappa_club IS
    'Mappa club fantacalcio (giocatore.club) -> nome ufficiale su Transfermarkt. Editabile a mano via SQL.';

INSERT INTO transfermarkt_mappa_club (club, nome_transfermarkt) VALUES
    ('Atalanta', 'Atalanta Bergamasca Calcio S.p.a.'),
    ('Bologna', 'Bologna Football Club 1909'),
    ('Cagliari', 'Cagliari Calcio'),
    ('Como', 'Calcio Como'),
    ('Fiorentina', 'Associazione Calcio Fiorentina'),
    ('Frosinone', 'Frosinone Calcio S.r.l.'),
    ('Genoa', 'Genoa Cricket and Football Club'),
    ('Inter', 'Football Club Internazionale Milano S.p.A.'),
    ('Juventus', 'Juventus Football Club'),
    ('Lazio', 'Società Sportiva Lazio S.p.A.'),
    ('Lecce', 'Unione Sportiva Lecce'),
    ('Milan', 'Associazione Calcio Milan'),
    ('Monza', 'Associazione Calcio Monza'),
    ('Napoli', 'Società Sportiva Calcio Napoli'),
    ('Parma', 'Parma Calcio 1913'),
    ('Roma', 'Associazione Sportiva Roma'),
    ('Sassuolo', 'Unione Sportiva Sassuolo Calcio'),
    ('Torino', 'Torino Calcio'),
    ('Udinese', 'Udinese Calcio'),
    ('Venezia', 'Venezia Football Club')
ON CONFLICT (club) DO UPDATE SET nome_transfermarkt = EXCLUDED.nome_transfermarkt;

-- Tabella UNICA: sia cache grezza dell'ultimo dump scaricato da transfermarkt-scraper
-- (una riga per giocatore TM, sovrascritta ad ogni run di scripts/match_transfermarkt.py),
-- sia coda di revisione. Le due cose sono la stessa tabella perché condividono gli
-- stessi dati: la coda è semplicemente il sottoinsieme di righe con `id_giocatore`
-- valorizzato.
--   - id_giocatore NULL          -> riga di sola cache, non richiede revisione
--   - id_giocatore valorizzato,
--     id_transfermarkt valorizzato -> candidato in revisione per quel nostro giocatore
--     (2+ righe con lo stesso id_giocatore = ambiguo)
--   - id_giocatore valorizzato,
--     id_transfermarkt NULL       -> riga sintetica "nessun candidato trovato" per quel
--     giocatore (nessun dato TM reale, solo il marcatore)
-- L'admin risolve un caso dalla pagina /admin/verifica_corrispondenze_giocatori: la riga
-- sintetica (se presente) viene eliminata, le righe di cache tornano a id_giocatore NULL.
CREATE TABLE IF NOT EXISTS transfermarkt_giocatori (
    id serial PRIMARY KEY,
    id_transfermarkt integer UNIQUE,
    club_tm text,
    nome text,
    cognome text,
    data_nascita date,
    scadenza_contratto date,
    id_giocatore integer REFERENCES giocatore(id),
    aggiornato_il timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE transfermarkt_giocatori IS
    'Cache dell''ultimo dump di transfermarkt-scraper (id_giocatore NULL) + coda di revisione (id_giocatore valorizzato = candidato/marcatore "non trovato" per quel nostro giocatore). Sovrascritta ad ogni run di scripts/match_transfermarkt.py.';

CREATE INDEX IF NOT EXISTS idx_transfermarkt_giocatori_club_tm
    ON transfermarkt_giocatori (club_tm);
CREATE INDEX IF NOT EXISTS idx_transfermarkt_giocatori_id_giocatore
    ON transfermarkt_giocatori (id_giocatore);
