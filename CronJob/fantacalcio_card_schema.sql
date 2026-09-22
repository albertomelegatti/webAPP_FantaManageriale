-- Id fantacalcio.it di ogni giocatore, per mostrare il "campioncino" (la card
-- ufficiale) invece del solo nome: https://content.fantacalcio.it/web/campioncini/
-- <stagione>/card/<id_fantacalcio>.png. Eseguire una tantum sul DB (es.
-- Supabase SQL editor).
--
-- La connessione usata da Claude Code verso questo DB è in sola lettura, quindi
-- questo script va lanciato manualmente.
--
-- Stesso schema del matching Transfermarkt (vedi
-- CronJob/transfermarkt_matching_schema.sql): una tabella di cache/coda che fa
-- doppio uso, dump grezzo scaricato (id_giocatore NULL) e coda di revisione per
-- i casi ambigui o non trovati (id_giocatore valorizzato). A differenza di
-- Transfermarkt qui non serve una mappa club - il nome del giocatore in questa
-- app arriva già dal listone di fantacalcio.it, quindi il match è per nome
-- esatto (normalizzato) senza bisogno di scoping per squadra.

ALTER TABLE giocatore
    ADD COLUMN IF NOT EXISTS id_fantacalcio integer;

-- Tabella UNICA: sia cache grezza dell'ultimo dump scaricato dalla pagina
-- quotazioni (una riga per giocatore fantacalcio.it, sovrascritta ad ogni
-- sincronizzazione), sia coda di revisione - le due cose condividono gli
-- stessi dati, la coda è il sottoinsieme di righe con `id_giocatore`
-- valorizzato. Stesso schema/significato di transfermarkt_giocatori:
--   - id_giocatore NULL                              -> riga di sola cache
--   - id_giocatore valorizzato, id_fantacalcio valorizzato -> candidato in
--     revisione per quel nostro giocatore (2+ righe con lo stesso
--     id_giocatore = ambiguo)
--   - id_giocatore valorizzato, id_fantacalcio NULL  -> riga sintetica
--     "nessun candidato trovato" per quel giocatore
CREATE TABLE IF NOT EXISTS fantacalcio_giocatori (
    id             serial PRIMARY KEY,
    id_fantacalcio integer UNIQUE,
    nome           text,
    squadra_fc     text,
    id_giocatore   integer REFERENCES giocatore(id),
    aggiornato_il  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fantacalcio_giocatori_id_giocatore
    ON fantacalcio_giocatori (id_giocatore);
