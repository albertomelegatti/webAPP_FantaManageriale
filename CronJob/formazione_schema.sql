-- Schema della formazione (campetto): modulo scelto da ogni squadra e i
-- giocatori assegnati a ciascuno dei suoi 11 slot (titolare e fino a 4
-- riserve). Eseguire una tantum sul DB (es. Supabase SQL editor).
--
-- La connessione usata da Claude Code verso questo DB è in sola lettura, quindi
-- questo script va lanciato manualmente.
--
-- Una riga per squadra, non una per slot: gli 11 slot del modulo, con
-- titolare e fino a 4 riserve per ciascuno (fino a 55 giocatori), stanno in
-- un unico campo JSONB invece che in una tabella figlia. Una tabella figlia
-- costerebbe fino a 55 righe a lettura e a scrittura per una sola squadra,
-- contro la query singola che il resto della pagina squadra già si tiene
-- stretta (vedi il docstring di app/services/dashboard.py). Gli id dei
-- giocatori dentro il JSON non sono vincolati da una foreign key - non è
-- possibile referenziare campi dentro un JSONB - la validazione (giocatore in
-- rosa, ruolo compatibile con lo slot, nessun doppio impiego) è applicativa,
-- ad ogni salvataggio: vedi app/services/formazione.py.

CREATE TABLE IF NOT EXISTS formazione (
    squadra        varchar PRIMARY KEY
                   REFERENCES squadra(nome) ON UPDATE CASCADE ON DELETE CASCADE,
    modulo         varchar NOT NULL,
    -- Un elemento per ciascuno degli 11 slot del modulo, nello stesso ordine
    -- di app/domini/moduli.py: MODULI[modulo]. Ogni elemento è un oggetto
    -- {"tit": id|null, "ris": [id, ...]} con fino a 4 riserve in ordine di
    -- chiamata. Le righe salvate prima hanno {"tit", "ris", "ter"} con un id
    -- ciascuno: l'app le legge ancora (moduli.normalizza_slot), nessuna
    -- migrazione necessaria.
    slot           jsonb NOT NULL DEFAULT '[]'::jsonb,
    aggiornata_il  timestamptz NOT NULL DEFAULT now()
);
