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
