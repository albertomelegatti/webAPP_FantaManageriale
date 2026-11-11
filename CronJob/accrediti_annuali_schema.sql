-- ============================================================================
-- Registro degli accrediti annuali: impedisce di accreditare due volte lo stesso
-- premio nella stessa stagione.
--
-- Due tipi di accredito, ciascuno con una chiave unica:
--   'albo_oro:<stagione>:<competizione>'   es. albo_oro:25-26:Campionato
--   'rendite_stadi:<stagione>'             es. rendite_stadi:26-27
--
-- L'accredito scrive prima la riga qui e poi somma i crediti, nella stessa
-- transazione: la chiave primaria e' la guardia. Due richieste simultanee non
-- passano entrambe, e ricaricare la pagina il giorno dopo non permette di
-- rifarlo (il gettone di sessione dell'accredito rendite proteggeva solo da un
-- doppio clic).
--
-- Script unico, idempotente, in una transazione sola (es. Supabase SQL editor):
-- va lanciato a mano, prima su dev e poi su prod. Finche' la tabella manca,
-- l'app rifiuta ogni accredito (meglio un avviso che un accredito senza guardia).
--
-- STORICO. Le competizioni dell'albo d'oro che hanno gia' crediti registrati
-- sono state accreditate a suo tempo (a mano, da Gestione Crediti): vanno
-- segnate come gia' fatte, altrimenti il pulsante le accrediterebbe una seconda
-- volta. Qui sotto lo fa l'INSERT ... SELECT, che prende le competizioni con
-- somma dei crediti > 0 (verificato su dev: 24-25 e 25-26, Campionato e Coppa;
-- 26-27 ha tutti 0 e resta accreditabile).
--
-- RENDITE DEGLI STADI. Non si sa se la rendita della stagione corrente sia gia'
-- stata accreditata: la tabella parte vuota per questo tipo. Se in produzione
-- e' gia' stata accreditata questa stagione, segnarlo PRIMA di usare il
-- pulsante, togliendo il commento alla riga in fondo (e adattando la stagione).
-- ============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS accrediti_annuali (
    chiave       varchar     PRIMARY KEY,
    tipo         varchar     NOT NULL CHECK (tipo IN ('albo_oro', 'rendite_stadi')),
    stagione     varchar     NOT NULL,
    competizione varchar,                       -- solo per 'albo_oro'
    eseguito_il  timestamptz NOT NULL DEFAULT now(),
    eseguito_da  varchar     NOT NULL,          -- l'admin, o 'storico' per le righe di questo script
    squadre      integer     NOT NULL DEFAULT 0,
    totale       integer     NOT NULL DEFAULT 0,
    storico      boolean     NOT NULL DEFAULT false
);

INSERT INTO accrediti_annuali (chiave, tipo, stagione, competizione, eseguito_da, squadre, totale, storico)
SELECT 'albo_oro:' || stagione || ':' || competizione, 'albo_oro', stagione, competizione,
       'storico', COUNT(DISTINCT squadra), SUM(crediti_generati), true
FROM albo_oro
GROUP BY stagione, competizione
HAVING SUM(crediti_generati) > 0
ON CONFLICT (chiave) DO NOTHING;

COMMIT;

-- Se la rendita degli stadi di questa stagione e' gia' stata accreditata a mano:
-- INSERT INTO accrediti_annuali (chiave, tipo, stagione, eseguito_da, storico)
-- VALUES ('rendite_stadi:26-27', 'rendite_stadi', '26-27', 'storico', true)
-- ON CONFLICT (chiave) DO NOTHING;
