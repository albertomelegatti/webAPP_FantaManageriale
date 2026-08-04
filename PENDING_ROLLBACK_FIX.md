# Fix per PendingRollbackError

## Problema

```
sqlalchemy.exc.PendingRollbackError: Can't reconnect until invalid transaction is rolled back
```

Questo errore accade quando:
1. Una query fallisce
2. La transazione rimane in stato "invalid"  
3. Una richiesta successiva tenta di usare la session senza rollback

## Soluzioni implementate

### 1. **Before Request Handler** (main.py)
Pulisce la session SQLAlchemy PRIMA di ogni richiesta:
```python
@app.before_request
def before_request():
    try:
        db.session.rollback()
        db.session.remove()
    except Exception:
        pass
```

### 2. **Teardown App Context Robusto** (main.py)
Cleanup aggressivo DOPO ogni richiesta:
```python
@app.teardown_appcontext
def teardown_db(exception):
    try:
        if exception:
            db.session.rollback()
        db.session.remove()
    except Exception as e:
        print(f"[ERROR] Teardown failed: {e}")
    finally:
        gc.collect()
```

### 3. **Error Handlers Globali** (main.py)
Cattura tutte le eccezioni e pulisce:
```python
@app.errorhandler(Exception)
def handle_exception(error):
    db.session.rollback()
    db.session.remove()
    gc.collect()
    return redirect(url_for('home')), 500
```

### 4. **Context Manager DatabaseConnection** (db.py)

Per le route psycopg2 (new), usa:
```python
from db import DatabaseConnection

@app.route("/esempio")
def esempio():
    with DatabaseConnection() as (conn, cur):
        # La transazione è auto-rollback-ata se c'è errore
        cur.execute("SELECT * FROM tabella")
        data = cur.fetchall()
    # Connessione auto-rilasciata qui
    return render_template("template.html", data=data)
```

### 5. **Improved release_connection** (db.py)
Adesso fa sempre rollback antes di restituire al pool:
```python
def release_connection(conn=None, cur=None):
    # Sempre chiudi il cursore
    if cur:
        cur.close()
    
    # Sempre rollback la transazione
    if conn and not conn.closed:
        conn.rollback()
    
    # Restituisci al pool o chiudi
    pool.putconn(conn, close=False)
```

## Come importare il context manager

```python
from db import DatabaseConnection

# Uso
@app.route("/data")
def get_data():
    with DatabaseConnection() as (conn, cur):
        cur.execute("SELECT nome FROM squadra")
        squadre = cur.fetchall()
    return render_template("squadre.html", squadre=squadre)
```

## Avvertenze

### ❌ VECCHIO (ERRATO - causerà PendingRollbackError):
```python
@app.route("/old")
def old_route():
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT * FROM squadra")
        # Se qui c'è errore, release_connection potrebbe non essere chiamato
    finally:
        release_connection(conn, cur)
        # Se release_connection fallisce, exception propagherà
```

### ✅ NUOVO (CORRETTO - PendingRollbackError evitato):
```python
@app.route("/new")
def new_route():
    with DatabaseConnection() as (conn, cur):
        cur.execute("SELECT * FROM squadra")
        squadre = cur.fetchall()
    # Cleanup automatico e sicuro
    return render_template("squadre.html", squadre=squadre)
```

## Verificare il fix

1. **Nei log di Render**, non dovrebbero più apparire:
   ```
   sqlalchemy.exc.PendingRollbackError
   ```

2. **Health check**:
   ```bash
   curl https://tuaapp.onrender.com/health
   # Dovrebbe tornare {"status": "ok"}
   ```

3. **Monitorare memoria e CPU**:
   - Render Dashboard → Metrics
   - Memoria non dovrebbe crescere continuamente
   - CPU dovrebbe tornare a baseline tra le richieste

## Prossimi passi (opzionale)

Se continua ad avere problemi, potremmo fare il refactor graduale di tutte le route per usare `DatabaseConnection`:
1. Apri il file da refactor (es. `user_aste.py`)
2. Sostituisci il try-except-finally tradizionale con context manager
3. Testa
4. Commit

Esempio di refactor per `user_aste.py`:
```python
# PRIMA
conn = None
cur = None
try:
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""SELECT ...""")
    data = cur.fetchall()
except Exception as e:
    print(f"Errore: {e}")
finally:
    release_connection(conn, cur)

# DOPO
with DatabaseConnection() as (conn, cur):
    cur.execute("""SELECT ...""")
    data = cur.fetchall()
```
