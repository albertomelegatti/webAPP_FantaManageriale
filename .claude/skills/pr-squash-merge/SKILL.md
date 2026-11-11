---
name: pr-squash-merge
description: Apre la pull request del branch corrente, la controlla (diff, test, CI, conflitti) e la mergia con squash merge. Usala ogni volta che l'utente dice "apri la PR", "fai la PR", "mergia", "mergia la PR", "squash and merge", "chiudi la PR" o chiede di portare il branch su main, anche se non nomina lo squash. Se la PR esiste gia', salta l'apertura e passa a controllo e merge.
---

# PR: apri, controlla, mergia (squash)

Il repo non ha CI ne' template di PR, quindi il "controllo" lo fai tu prima di
mergiare. Su `main` la storia resta lineare e leggibile: un commit per PR, con
titolo `Titolo della PR (#N)`. Per questo si usa lo squash e non il merge commit.

## 1. Stato di partenza

Esegui, e leggi l'output prima di agire:

```bash
git status -sb
git branch --show-current
gh pr list --head "$(git branch --show-current)" --state all --json number,title,state,url
```

- Se sei su `main`, fermati: non c'e' niente da aprire. Chiedi quale branch.
- Se ci sono modifiche non committate o commit non pushati, dillo e chiedi se
  includerli. File non tracciati che non c'entrano (es. script SQL in lavorazione)
  non vanno aggiunti di tua iniziativa.
- Se una PR esiste gia' ed e' `OPEN`, salta al punto 3. Se e' `MERGED`, dillo e basta.

## 2. Apri la PR

1. `git push -u origin <branch>` se il branch non e' sul remoto.
2. Leggi cosa cambia davvero: `git log main..HEAD --oneline` e `git diff main...HEAD --stat`
   (e il diff completo dei file che contano). Il testo della PR deve descrivere
   il diff, non quello che ricordi di aver fatto.
3. Titolo breve in italiano, nello stile dei commit recenti (`git log main --oneline -8`),
   senza il `(#N)`: lo aggiunge GitHub con lo squash.
4. Corpo in italiano, con queste sezioni (salta quelle vuote, ma tieni "Test"):
   - **Cosa cambia**: elenco puntato per funzione/pagina, in parole da utente.
   - **Prima del deploy**: migrazioni SQL o script da lanciare a mano (prima dev, poi prod),
     variabili d'ambiente nuove. E' la sezione che evita incidenti in produzione.
   - **Da sapere**: effetti collaterali, comportamenti cambiati, cose non fatte.
   - **Test**: cosa hai lanciato e con che esito, e cosa NON hai verificato
     (es. aspetto nel browser). Non scrivere "passano" se non li hai eseguiti.
5. Chiudi il corpo con la riga di attribuzione richiesta dall'harness per le PR.
6. `gh pr create --base main --title ... --body-file <file>`; scrivi il corpo in un
   file temporaneo (scratchpad) per evitare problemi di quoting, poi riporta l'URL.

## 3. Controlla

Fai questi controlli e riporta l'esito in poche righe. Non mergiare in silenzio se
uno fallisce.

- `gh pr view <N> --json state,mergeable,mergeStateStatus,reviewDecision,statusCheckRollup`
  - `mergeable` deve essere `MERGEABLE`. Con `CONFLICTING` fermati e proponi come risolvere.
  - Una `statusCheckRollup` vuota e' normale qui (nessuna CI): non e' un errore.
  - Se ci sono check, devono essere tutti verdi; se sono in corso, aspetta.
- Test in locale se il repo li ha (`pytest`, vedi `tests/`). Sono falliti dei test?
  Distingui i fallimenti noti (in locale falliscono i test `os.fork` su Windows)
  da quelli nuovi. Un fallimento nuovo blocca il merge.
- Rilettura veloce del diff cercando cio' che non deve finire su `main`: segreti,
  `.env`, file di debug, `print` dimenticati, SQL distruttivo non dichiarato nel corpo.
- Se la PR ha una sezione "Prima del deploy", ricordala all'utente prima di mergiare:
  il merge su `main` puo' mandare il codice in produzione.

## 4. Mergia (squash)

Mergia solo se l'utente l'ha chiesto ("mergia", "e mergia", "chiudi"). Se ha chiesto
solo di aprire la PR, fermati dopo il punto 3 e chiedi.

```bash
gh pr merge <N> --squash
gh pr view <N> --json state,mergedAt,mergeCommit
```

- Lo squash prende titolo e corpo dalla PR. Se il corpo e' lungo va bene lo stesso,
  ma non passare `--subject`/`--body` diversi senza motivo: titolo PR e commit su `main`
  devono coincidere.
- Non usare `--admin` per scavalcare un blocco e non usare `--merge` o `--rebase`:
  se lo squash e' rifiutato, riporta l'errore e chiedi.
- Non cancellare il branch (ne' remoto ne' locale) a meno che l'utente lo chieda:
  con lo squash il branch non risulta "mergiato" per git, quindi `git branch -d`
  si rifiuterebbe comunque.

## 5. Dopo il merge

Conferma in una riga: numero PR, stato `MERGED`, ora. Poi, solo se l'utente vuole
continuare a lavorare, `git checkout main && git pull`. Se la PR aveva passaggi
"Prima del deploy", ripeti l'elenco come promemoria finale.
