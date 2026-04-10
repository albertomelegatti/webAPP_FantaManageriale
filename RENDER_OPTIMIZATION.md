# Ottimizzazioni per Render - Worker Timeout & Memory Issues

## Problemi risolti

### 1. **WORKER TIMEOUT** 
Errore: `[CRITICAL] WORKER TIMEOUT (pid:58)`

❌ **Prima**: `--timeout 120` (2 minuti)
✅ **Dopo**: `--timeout 300` (5 minuti)

### 2. **Numero di Worker insufficiente**
❌ **Prima**: 1 worker (default)
✅ **Dopo**: 4 worker con 2 thread ciascuno (gthread)

```
Prima: gunicorn --preload main:app --timeout 120

Dopo: gunicorn --preload main:app \
  --timeout 300 \
  --workers 4 \
  --threads 2 \
  --worker-class gthread \
  --max-requests 1000 \
  --max-requests-jitter 100
```

### 3. **Connection Pool insufficiente**
❌ **Prima**: minconn=2, maxconn=20
✅ **Dopo**: minconn=5, maxconn=50 con timeout di connessione

### 4. **Memory Leak dalle Sessioni Flask**
❌ **Prima**: SESSION_PERMANENT=365 giorni
✅ **Dopo**: SESSION_PERMANENT=30 giorni + garbage collection

### 5. **No health check**
✅ **Nuovo**: Endpoint `/health` per monitorare lo stato

## Cambiamenti fatti

### `Procfile`
- ⬆️ Timeout: 120s → 300s
- ⬆️ Worker: 1 → 4
- ⬆️ Threads: 1 → 2
- ✨ worker-class: gthread (thread-based, migliore per I/O)
- ✨ max-requests: ricicla worker ogni 1000 richieste
- ✨ max-requests-jitter: evita spike di memoria

### `db.py`
- ⬆️ Connection pool: 2-20 → 5-50
- ✨ connect_timeout: 10 secondi
- ✨ getconn(timeout=5): timeout su acquisizione connessione
- ✨ Logging pool status

### `main.py`
- ✨ SQLAlchemy pool_recycle: ricicla connessioni ogni ora
- ✨ pool_pre_ping: verifica connessioni prima di usarle
- ⬇️ SESSION_LIFETIME: 365 → 30 giorni
- ✨ gc.collect() nel teardown
- ✨ Endpoint `/health` con health check

## Come monitorare

### 1. **Logs di Render**
```
In Render Dashboard → Logs
Cerca: [POOL STATUS] per vedere connessioni attive/libere
Cerca: WORKER per debug worker
```

### 2. **Health check**
```bash
curl https://tuo-app.onrender.com/health
```

### 3. **CPU/Memoria**
In Render Dashboard → Metrics monitorare:
- CPU usage (dovrebbe stare sotto 50%)
- Memory (dovrebbe oscillare, non crescere continuamente)

## Prossimi step se persistono i problemi

### Se memoria continua a crescere:
1. CHECK: Query N+1 nei blueprint (user_aste.py, user_rosa.py, etc)
   ```python
   # ❌ BAD: Query in loop
   for asta in aste_raw:
       cur.execute(f"SELECT ... WHERE id = {asta['id']}")  # N queries!
   
   # ✅ GOOD: Una query con JOIN
   cur.execute("SELECT ... WHERE id IN (...)")
   ```

2. CHECK: Sessioni non rilasciate
   - Aggiungere `session.clear()` su logout
   - Usare context manager: `with get_connection() as conn:`

### Se timeout persiste:
1. Aumentare a 600s nel Procfile
2. Identificare query lente con EXPLAIN ANALYZE su PostgreSQL

## File di configurazione consigliati per Render

### render.yaml (opzionale, per auto-deploy)
```yaml
services:
  - type: web
    name: fanta-manager
    runtime: python
    pythonVersion: 3.11
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn --preload main:app --timeout 300 --workers 4 --threads 2 --worker-class gthread
    envVars:
      - key: PYTHON_ENV
        value: production
```

## Verifica dei fix

✅ Worker timeout ridotti
✅ Memory usage più stabile
✅ Connessioni al DB gestite meglio
✅ Health check disponibile
✅ Garbage collection attivo
