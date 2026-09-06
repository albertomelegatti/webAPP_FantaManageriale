# Draft U21 — registrare l'esito

Il draft si svolge fuori dall'app: chi lo conduce tiene il tabellone e alla fine
consegna un file con le trenta scelte. Questo script lo trasforma in scritture
sul database — giocatori assegnati e pick consumate — e annuncia il risultato
nel gruppo Telegram.

## L'ingresso

Un **CSV** con una riga per scelta e queste colonne, lette per nome (l'ordine
non conta, colonne in più vengono ignorate):

| colonna | cosa contiene |
|---|---|
| `Squadra` | la fantasquadra, anche scritta all'ingrosso: "Zero Dayz" trova "ZeroDayz FC" |
| `Pick` | il **giro** della scelta: 1, 2 o 3 |
| `Ruolo` | serve solo da controllo: se non combacia col ruolo che il giocatore ha in tabella, esce un avviso |
| `Calciatore` | il nome come lo scrive la lega |
| `Punteggio` | facoltativo, si stampa e basta: non è un prezzo in crediti |

Il separatore può essere virgola, punto e virgola o tabulazione: lo riconosce da
sé. In `storico/` c'è il file dell'anno passato, che vale da esempio — e i nomi
lì dentro sono quelli **giusti**, come li scrive la lega: se l'export del draft
arriva con un nome tagliato o con un refuso, si corregge nel CSV prima di
lanciare, non si insegna al programma a tradurlo.

## La procedura, dall'inizio alla fine

1. **Prova a vuoto su dev.** Il `.env` del repo punta allo sviluppo, quindi
   basta lanciarlo:

       python scripts/draft_u21/assegna.py --input draft_2027.csv

   Non scrive niente: stampa chi va dove, con quale pick, e il testo della
   comunicazione. **È il passaggio che va guardato con gli occhi**, riga per
   riga — è l'unico momento in cui un errore costa zero.

2. **Sistema il CSV.** Se un nome non viene riconosciuto — «non è fra gli
   svincolati» — si corregge lì, col nome per esteso della lega. Gli avvisi sul
   ruolo invece dicono che il nome sulla riga non è il giocatore che ci si
   aspetta: quasi sempre è una colonna del CSV ordinata per conto suo. Si
   sistema il file e si rilancia la prova a vuoto finché è pulita.

3. **Prova generale su dev**, stavolta davvero:

       python scripts/draft_u21/assegna.py --input draft_2027.csv --scrivi

   Poi si guarda il risultato sul sito in locale (`python wsgi.py`, porta 8080):
   le rose devono avere tre primavera in più a squadra e le pick dell'anno
   devono risultare tutte usate, col nome accanto. In sviluppo
   `NOTIFICHE_ATTIVE=false`, quindi non parte nessun messaggio — e siccome la
   riga in `movimenti_squadra` la salva la stessa funzione che invia, in dev
   non viene scritta nemmeno quella.

4. **Produzione**, con l'indirizzo del database di prod e le notifiche accese:

       NOTIFICHE_ATTIVE=True DATABASE_URL='<url di prod>' \
         python scripts/draft_u21/assegna.py --input draft_2027.csv --scrivi

5. **Controprova**: rilanciare la prova a vuoto su prod. Deve fermarsi dicendo
   che il primo giocatore non è più fra gli svincolati — è il segno che la
   scrittura è arrivata, e che un secondo lancio per sbaglio non raddoppierebbe
   niente.

## Cosa scrive

Tutto dentro una transazione sola, che si annulla per intero al primo intoppo:

- `giocatore`: `tipo_contratto` a `Primavera`, `squadra_att` e
  `detentore_cartellino` alla fantasquadra che ha scelto;
- `draft`: `id_giocatore_scelto` sulla pick di quella squadra in quel giro;
- la comunicazione nel gruppo, che salva da sé la riga in `movimenti_squadra`.

I crediti non si toccano: al draft non si paga in crediti.

L'anno lo decide da solo — il primo con pick ancora libere — e si può forzare con
`--anno`. L'annuncio si salta con `--senza-annuncio`.

## Le difese

Lo script preferisce fermarsi che indovinare, perché un id sbagliato regala un
giocatore alla squadra sbagliata. Non ha nessuna tabella di corrispondenze
interna: il nome sbagliato si corregge nel file, che è dove il dato vive.

Si ferma **senza scrivere niente** se un nome non corrisponde a un solo svincolato, se lo stesso giocatore risulta scelto due
volte, se una squadra non ha una pick libera in quel giro, e — durante la
scrittura — se un giocatore nel frattempo non è più svincolato o la pick è già
stata consumata da qualcun altro.

## Storia

- **2026**: primo anno con questo script. Trenta scelte, tre per squadra,
  eseguite prima su dev come prova generale e poi in produzione il 6 settembre
  2026, con annuncio nel gruppo. L'ingresso era un xlsx; la conversione in CSV
  è in `storico/2026.csv`, con tre nomi corretti a mano che nell'originale
  arrivavano tagliati dalla colonna stretta (Robinho Junior, Rodriguez Ju.) o
  con un refuso (Fernandez T.).
