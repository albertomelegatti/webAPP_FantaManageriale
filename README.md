# Fanta Manageriale

Una piattaforma web completa per la gestione di un campionato di fantacalcio. Consente alle squadre di partecipare ad aste, gestire trasferimenti di giocatori, organizzare prestiti e coordinare scambi, il tutto attraverso un'interfaccia intuitiva con notifiche in tempo reale via Telegram.

## Caratteristiche Principali

### Gestione Aste
- Creazione e gestione centrallizzata di aste per i giocatori
- Sistema di iscrizione con riserve per evitare race condition
- Transizioni di stato automatiche: mostra interesse → in corso → conclusa
- Notifiche Telegram per inizio e fine aste
- Storico completo delle partecipazioni

### Sistema di Prestiti
- Richiesta e gestione prestiti tra squadre
- Configurazione flessibile: costo del prestito e crediti di riscatto
- Meccanismo di accettazione/rifiuto bidirezionale
- Supporto per prestiti associati a scambi complessi
- Notifiche Telegram per riposte alle richieste

### Mercato e Scambi
- Proposte di scambio bilaterali tra squadre
- Combinazione di trasferimenti di giocatori e prestiti in un'unica transazione
- Sistema di crediti per limitare gli scambi non equilibrati
- Cronologia completa delle proposte di mercato
- Accettazione/rifiuto con notifiche Telegram

### Gestione Rosa
- Visualizzazione della rosa completa di ogni squadra
- Gestione della primavera: promozione in prima squadra e tagli
- Quotazioni giocatori in tempo reale
- Tracking dello stato contrattuale (indeterminato, primavera, svincolato)
- Supporto per giocatori in prestito

### Area Amministrativa
- Dashboard amministratore con controllo totale
- Gestione crediti squadre
- Monitoraggio comunicazioni tra squadre
- Gestione richieste di modifica contratto
- Interfaccia dedicate per le operazioni critiche

### Chatbot Regolamentare
- Assistente AI basato su OpenAI che risponde a domande sul regolamento
- Utilizza Deepseek per risposte accurate e contestuali
- Consulenza istantanea alle regole del campionato
- Disponibile direttamente nell'interfaccia web

### Notifiche in Tempo Reale
- Bot Telegram integrato per aggiornamenti istantanei
- Notifiche per: iscrizioni aste, risposte prestiti, esiti scambi, promozioni, tagli
- Comunicazioni dirette tra amministrazione e squadre
- Sistema webhook per aggiornamenti dal database

## Tech Stack

### Backend
- **Framework**: Flask 3.0.0 - microframework Python leggero e scalabile
- **Linguaggio**: Python 3.11
- **Gestione Database**: SQLAlchemy ORM + psycopg2
- **Server**: Gunicorn web server con preload per prestazioni
- **Sessioni**: Flask-Session con database backend

### Database
- **Sistema**: PostgreSQL (Supabase Hosted)
- **Connection Pooling**: ThreadedConnectionPool per gestione efficiente connessioni
- **Integrazione**: Webhook real-time per aggiornamenti aste
- **Gestione Transazioni**: Isolation level REPEATABLE_READ per integrità dati

### Frontend
- **Template Engine**: Jinja2 (integrato Flask)
- **Styling**: CSS custom + dark mode
- **Interattività**: JavaScript vanilla
- **Interfaccia Responsiva**: HTML5 semantico

### Integrazioni Esterne
- **Telegram API**: Notifiche real-time e gestione bot
- **OpenAI / NVIDIA API**: Chatbot regolamentare con modello Deepseek
- **Supabase**: Hosting PostgreSQL con webhook

### DevOps & Deployment
- **Containerization**: Docker + Docker Compose
- **Base Image**: Python 3.11-slim
- **Dipendenze di Sistema**: gcc, postgresql-client
- **Orchestration**: Docker Compose per ambiente locale
- **Procfile**: Supporto Heroku per deployment in cloud

## Struttura del Progetto

```
├── main.py                    # Applicazione Flask principale
├── admin.py                   # Blueprint area amministrativa
├── user.py                    # Blueprint autenticazione e dashboard utente
├── user_aste.py              # Gestione partecipazione aste
├── user_prestiti.py          # Gestione richieste prestiti
├── user_mercato.py           # Gestione scambi giocatori
├── user_rosa.py              # Gestione rosa e primavera
├── chatbot.py                # Assistente AI regolamentare
├── webhook.py                # Webhook per aggiornamenti real-time
├── telegram_utils.py         # Utilità notifiche Telegram
├── db.py                     # Gestione connessioni database
├── queries.py                # Funzioni query ricorrenti
├── Dockerfile                # Configurazione container
├── docker-compose.yml        # Orchestrazione servizi
├── requirements.txt          # Dipendenze Python
├── regolamento.txt           # Testo regolamento (input chatbot)
├── templates/                # Template HTML Flask
├── static/                   # Asset statici (CSS, JS, immagini)
└── TelegramBot/             # Script utilità Telegram bot
```

## Backend Database (Supabase)

L'applicazione utilizza **Supabase** per l'hosting del database PostgreSQL e sfrutta le seguenti funzionalità:

- **Tables Principali**: squadra, giocatore, asta, prestito, scambio
- **Real-time Webhooks**: Configurati per aggiornamenti dello stato aste
- **Connection Pool**: Gestione efficiente connessioni con minconn=1, maxconn=5
- **Authentication URL**: Ereditata dalla stringa di connessione

### Webhook Implementati

Il webhook `/webhook/update_stato_asta` riceve aggiornamenti da Supabase quando cambia lo stato di un'asta e:
- Invia notifica Telegram quando un'asta inizia (mostra_interesse → in_corso)
- Invia notifica quando un'asta conclude (in_corso → conclusa)

## Deployment in Cloud

L'applicazione è predisposta per il deploy su piattaforme cloud:

- **Heroku**: Utilizza `Procfile` per esecuzione con Gunicorn
- **AWS/Docker**: Esegui il container Docker
- **Google Cloud Run**: Compatibile con immagine Docker

Beispiel Heroku:
```bash
git push heroku main
heroku config:set DATABASE_URL=...
heroku logs --tail
```

## Struttura Dati Chiave

### Squadra
- Nome, crediti, giocatori attuali

### Giocatore
- Nome, ruolo, squadra attuale, detentore cartellino, quotazione
- Tipo contratto (Indeterminato, Primavera, Svincolato)

### Asta
- Giocatore, partecipanti, stato (mostra_interesse/in_corso/conclusa)
- Data inizio/fine

### Prestito
- Squadra prestante, squadra ricevente, giocatore
- Costo prestito, crediti riscatto, stato

### Scambio
- Squadra proponente, squadra destinataria
- Giocatori offerti/richiesti, prestiti associati

## Sicurezza

- Password hashate con werkzeug.security
- Sessioni persistenti con scadenza annuale
- ACID transactions con isolation REPEATABLE_READ
- Protezione contro race condition con row-level locking (FOR UPDATE)
- Input validation per operazioni finanziarie (crediti, offerte)

## Performance

- Connection pooling per ridurre overhead connessioni
- Query ottimizzate con indici database
- Caching sessioni utente
- Asset statici serviti da directory dedicata
- Timeout Gunicorn di 120 secondi per operazioni lunghe

## Logging

- Log configurato per escludere richieste statiche (CSS, JS, immagini)
- Debug output per operazioni critiche database
- Webhook logging per troubleshooting real-time

## Installazione e Setup

### Prerequisiti

- Python 3.11+
- Docker e Docker Compose
- Account Supabase con database PostgreSQL creato
- Token bot Telegram
- API key OpenAI/NVIDIA (opzionale per chatbot)

### Setup Locale

1. **Clonare il repository**
   ```bash
   git clone <repository-url>
   cd webAPP_FantaManageriale
   ```

2. **Configurare le variabili d'ambiente**
   Creare un file `.env` nella root:
   ```
   SECRET_KEY=your-secret-key-here
   DATABASE_URL=postgresql://user:password@host:5432/dbname
   OPENAI_API_KEY=your-api-key
   TELEGRAM_BOT_TOKEN=your-bot-token
   FLASK_ENV=production
   ```

3. **Installare dipendenze Python**
   ```bash
   pip install -r requirements.txt
   ```

4. **Eseguire l'applicazione localmente**
   ```bash
   python main.py
   ```
   L'applicazione sarà disponibile su `http://localhost:5000`

### Setup con Docker

1. **Build e launch con Docker Compose**
   ```bash
   docker-compose up --build
   ```
   Il servizio web sarà accessibile su `http://localhost:5000`

2. **File di configurazione**
   - `Dockerfile`: Imposta Python 3.11-slim, installa dipendenze, espone porta 5000
   - `docker-compose.yml`: Configura il servizio web, monta volumi, inoltra variabili d'ambiente

### Variabili d'Ambiente Richieste

| Variabile | Descrizione |
|-----------|----------|
| `SECRET_KEY` | Chiave segreta per sessioni Flask |
| `DATABASE_URL` | Connection string PostgreSQL (Supabase) |
| `OPENAI_API_KEY` | API key per servizi OpenAI/NVIDIA |
| `TELEGRAM_BOT_TOKEN` | Token bot Telegram per notifiche |
| `FLASK_ENV` | Ambiente (development/production) |

## Licenza

Progetto privato. Tutti i diritti riservati.

