# Suite di test

Rete di sicurezza per il refactoring: serve a dimostrare che il comportamento
dell'app non cambia prima e dopo ogni fase.

## Come si esegue

```bash
venv/bin/python -m pip install -r requirements-dev.txt
venv/bin/python -m pytest                     # tutta la suite
venv/bin/python -m pytest -m "not db"         # solo funzioni pure, senza database
venv/bin/python -m pytest --cov=. --cov-report=term-missing
```

## Cosa contiene

| File | Copre | Database |
|---|---|---|
| `test_domini_puri.py` | ordinamento ruoli, formattazione date, matching Transfermarkt, anni prestito | no |
| `test_smoke_routes.py` | tutte le route GET rispondono senza 5xx | sì, sola lettura |
| `test_core_db.py` | ciclo di vita delle connessioni, ripristino dell'isolamento, commit/rollback | sì, sola lettura |
| `test_core_logging_errori.py` | eccezioni di dominio, configurazione del logging, conservazione dello stack trace | no |
| `test_url_for.py` | ogni endpoint citato in un `url_for` esiste davvero | sì, sola lettura |
| `test_scrittura_rosa.py` | taglio di un giocatore: costo, svincolo, vetrina | sì, **in scrittura isolata** |
| `test_scrittura_mercato.py` | accettazione e rifiuto di uno scambio | sì, **in scrittura isolata** |
| `test_scrittura_prestiti.py` | attivazione e rifiuto di un prestito, atomicità dei crediti | sì, **in scrittura isolata** |

## Sicurezza

I test girano contro il database Supabase **di sviluppo** puntato da `DATABASE_URL`.

- `pytest_configure` interrompe la sessione se l'ambiente sembra produzione
  (`RENDER` impostata o `FLASK_ENV=production`).
- Impostando `TEST_DB_PROJECT_REF` con il project ref Supabase atteso, la suite
  rifiuta di partire se `DATABASE_URL` punta a un progetto diverso. Consigliato.
- Le notifiche Telegram sono neutralizzate a livello di sessione: nessun
  messaggio parte durante i test.
- Tutti i test di questa fase esercitano **solo route GET**: sono di sola lettura
  per costruzione.

## Nota sui gate mercato/aste

I blueprint `mercato`, `aste` e `prestiti` hanno un `before_request` che
reindirizza quando la sezione è chiusa. Se nel DB di sviluppo le date di chiusura
sono passate, il corpo di quelle route non verrebbe mai eseguito e gli smoke test
resterebbero verdi coprendo solo il redirect. La fixture `gate_aperto` neutralizza
i gate lato test (senza scrivere sul DB) proprio per evitare questo falso senso di
sicurezza.

## Test che scrivono

I file `test_scrittura_*.py` esercitano i percorsi che muovono crediti e slot.
Girano contro il database di sviluppo **scrivendo davvero**, ma dentro una
transazione annullata alla fine (fixture `db_isolato`).

I confini di transazione delle route non vengono ignorati: sono emulati con i
savepoint (`tests/isolamento.py`), quindi `conn.commit()` diventa
`RELEASE SAVEPOINT` + `SAVEPOINT` e `conn.rollback()` diventa
`ROLLBACK TO SAVEPOINT`. Una route che fa rollback su errore si comporta quindi
esattamente come in produzione, e il test puo' verificarlo, ma nulla sopravvive.

Verificato confrontando un'istantanea del database prima e dopo l'intera suite:
conteggi di giocatori, scambi, prestiti, vetrina, svincolati e somma dei crediti
restano identici.

### Un difetto documentato, non ancora corretto

`test_scrittura_prestiti.py` contiene un test marcato `xfail(strict=True)` che
descrive il comportamento *corretto* dello spostamento crediti. Oggi fallisce,
perche' `sposta_crediti()` committa la transazione del chiamante. Quando la
Fase 8 lo correggera', il test passera' e la marcatura `strict` fara' fallire la
suite per ricordare di rimuoverla.
