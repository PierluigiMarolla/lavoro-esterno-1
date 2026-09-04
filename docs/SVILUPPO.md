# Guida per sviluppatori - Lavoro Esterno

## 1. Prerequisiti

- Docker e Docker Compose (plugin `docker compose`, non il vecchio
  `docker-compose` standalone).
- Python 3.13 e [uv](https://github.com/astral-sh/uv) (gestione
  dipendenze/venv del backend, usato anche in CI).
- Node.js (versione 20+) e npm (frontend React/Vite/TypeScript).
- Facoltativo per sviluppo locale senza Docker: PostgreSQL 17 e Redis
  installati localmente (in generale è più semplice usare i servizi
  `postgres`/`redis` già definiti nel `docker-compose.yml`).

## 2. Avvio ambiente locale

```bash
# 1. Copiare il file di esempio delle variabili d'ambiente
cp .env.example .env

# 2. Generare le chiavi di cifratura/JWT richieste (valori diversi per
#    ogni sviluppatore/ambiente, non riutilizzare quelli di esempio)
openssl rand -base64 32   # -> PHONE_ENCRYPTION_KEY (deve decodificare a 32 byte)
openssl rand -base64 32   # -> PHONE_HMAC_SECRET
openssl rand -base64 64   # -> JWT_SECRET_KEY (unica chiave, usata sia per access sia per refresh token)
# Incollare i valori generati nel file .env (mai committarlo)

# 3. Costruire e avviare l'intero stack
docker compose up --build

# 4. Applicare le migrazioni (il DB parte vuoto, le migrazioni non sono
#    automatiche all'avvio del container api)
docker compose exec api alembic upgrade head

# 5. Creare il primo utente Admin: nessun endpoint API può farlo (la
#    creazione utenti via API richiede già un Admin con 2FA attiva), quindi
#    va fatto con questo script una tantum, fuori dal perimetro HTTP/RBAC
#    (vedi backend/app/scripts/create_admin.py per i dettagli):
docker compose exec api python -m app.scripts.create_admin \
    --email admin@lavoro.internal --password "una-password-forte"

# 6. Creare le fonti da scrapare: nessun seed automatico, si usa il CRUD
#    completo via API/UI (POST /sources, form "Add Source" nella pagina
#    Sources — vedi docs/API.md e § 5 sotto). /sources e /search restano
#    vuoti finché non se ne crea almeno una.
```

Questa intera sequenza (`docker compose up --build`, migrazioni, creazione
admin, login) è stata eseguita ed è stata verificata contro un ambiente
Docker reale: build delle 6 immagini custom, avvio dei 13 servizi (+ 2
servizi di backup, vedi § 8), `POST /api/v1/auth/login` funzionante con la
coppia access/refresh token e l'oggetto `user` atteso dal frontend.

Servizi raggiungibili dopo l'avvio:

- Frontend/API tramite reverse proxy: `http://localhost/`
- Documentazione API interattiva: `http://localhost/docs`
- Console MinIO: `http://localhost:9001`
- Grafana: `http://localhost:3000` (utente `admin`, password da
  `GF_SECURITY_ADMIN_PASSWORD`)
- Prometheus: `http://localhost:9090`

Grafana carica automaticamente le dashboard del folder **Lavoro Esterno** e
gli alert. L'endpoint `http://api:8000/metrics` è deliberatamente interno: una
richiesta host a `/metrics` raggiunge il frontend, non FastAPI.

In sviluppo attivo sul frontend, è comune eseguire `npm run dev` in
locale (porta 5173 con hot reload di Vite) invece di ricostruire il
container ad ogni modifica, puntando `VITE_API_URL` all'API esposta dal
reverse proxy o direttamente dal container `api`.

## 3. Migrazioni database (Alembic)

Le migrazioni vivono in `backend/migrations/`. Comandi tipici (da
eseguire nel container `api` o in un ambiente Python locale con le
stesse dipendenze):

```bash
# Dentro il container api
docker compose exec api alembic upgrade head

# Creare una nuova migrazione dopo aver modificato i modelli SQLAlchemy
docker compose exec api alembic revision --autogenerate -m "descrizione modifica"

# Verificare la migrazione generata prima di applicarla: l'autogenerate
# di Alembic non è infallibile, va sempre riletta a mano.
docker compose exec api alembic upgrade head
```

In locale (senza Docker), equivalente con `uv`:

```bash
cd backend
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "descrizione modifica"
```

## 4. Test

### Backend

```bash
cd backend
uv sync --group dev
uv run ruff check .        # lint
uv run pytest -v           # test (stesso comando usato in CI, vedi .github/workflows/ci.yml)
```

I test che richiedono DB/Redis devono puntare a istanze di test (non a
quelle di sviluppo con dati reali) — usare variabili d'ambiente dedicate
o un container Postgres/Redis effimero, come fatto in CI.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run build
# npm run test (se/quando configurato un runner, es. Vitest)
```

## 5. Aggiungere una nuova fonte in `sources`

Il progetto non ha (più) connettori Python per-sito: l'unico motore di
scraping è quello generico configurabile, guidato interamente da
`Source.scrape_config` (§ 6 sotto) — nessun codice da scrivere per
aggiungere una fonte.

- Esiste un CRUD completo via API/UI (`POST /sources`, `PATCH
  /sources/{id}`, `DELETE /sources/{id}`, form "Add/Edit Source" nella
  pagina Sources — vedi `docs/API.md`) per creare/configurare una fonte.
- Dopo aver creato/configurato la fonte: `POST
  /api/v1/sources/{source_id}/scan` accoda un run reale (coda `scraping`,
  vedi `backend/app/workers/tasks_scraper.py`) — controllare
  `scrape_runs`/`scrape_errors` (o il drill-down nella UI) prima di
  lasciare la fonte attiva su uno schedule. Una fonte senza
  `scrape_config` fallisce esplicitamente il run (nessuna azione
  possibile senza una configurazione).

## 6. Configurare il motore di scraping generico

`app/scrapers/generic.py:GenericScraper` esegue scraping REALE tramite
Scrapling (`fetchMode: "http"` per richieste HTTP, `"dynamic"` per browser
headless, `"stealth"` per opzioni anti-bot) per qualunque fonte, guidato da
`Source.scrape_config` — nessun sito specifico è hardcoded nel motore. È
l'unico modo per attivare una fonte, PURCHÉ prima si verifichino ToS/
robots.txt per quel sito specifico (vedi PROGETTO.md § 4 sul perché questo
progetto non lo fa per te).

1. Nel form "Add Source" (o via `PATCH /sources/{id}` con `scrapeConfig`),
   fornire: uno o più `startUrls` (pagine di elenco annunci),
   `adLinkSelector` (selettore CSS dei link ai singoli annunci),
   opzionalmente `nextPageSelector` (paginazione), `fetchMode`,
   `userAgent`, opzioni browser/stealth (`waitSelector`, `waitMs`,
   `solveCloudflare`, `blockWebrtc`, `hideCanvas`, `realChrome`,
   `blockAds`, `proxy`) e i `fields` da estrarre da ogni pagina annuncio
   (selettore CSS + `attribute` `text`/`href`/`src` + `multiple` per liste
   come le immagini). Un campo `phone` è obbligatorio: senza telefono un
   annuncio non può essere collegato a nessun Record.
2. Usare "Check robots.txt" per verificare che il sito non vieti
   esplicitamente l'accesso (il motore lo verifica comunque ad ogni
   richiesta reale, ma è utile saperlo prima).
3. Usare "Test configuration" (`POST /sources/{id}/test-config`, richiede
   la fonte già salvata) per provare i selettori su UN solo annuncio reale
   senza scrivere nulla su database/MinIO — utile per iterare rapidamente
   sui selettori CSS ispezionando l'HTML del sito target nel browser.
4. Solo quando l'estrazione di prova è corretta, lanciare uno scan reale
   (`POST /sources/{id}/scan` o il bottone "Run Scan" in UI, visibile solo
   quando `hasScrapeConfig` è vero).

Rate limiting (minimo 1s tra le richieste) e rispetto di `robots.txt` sono
applicati SEMPRE dal motore, non sono opzioni disattivabili dalla
configurazione. Se `userAgent` non viene configurato, il motore usa il
default `LavoroEsternoBot/...`.

## 7. Pipeline AI e media

FFmpeg è installato nell'immagine backend/worker. In locale verificare con
`ffmpeg -version`; la suite genera un MP4 sintetico e controlla transcodifica,
thumbnail e frame senza includere materiale sensibile nel repository.

Il default è Ollama locale con `gemma4:e2b`: `ollama-init` scarica il modello
nel volume persistente al primo avvio e il worker AI parte solo al termine.
La configurazione è disponibile in `/settings/ai`. I provider cloud richiedono
una credenziale salvata, un test riuscito e budget token positivo; budget zero
non blocca Ollama. Prima di salvare credenziali generare una chiave AES da 32
byte in base64 e impostarla come `AI_CREDENTIAL_ENCRYPTION_KEY`. Il prompt
corrente è `summary-v1`: modificarlo richiede una nuova versione e il
superamento dei test/dataset in `backend/tests/fixtures/summary_eval.json`.

Comandi locali di verifica:

```bash
cd backend
uv sync --group dev
uv run ruff check .
uv run pytest -q
cd ../frontend
npm ci
npm run lint
npm run build
```

`MINIO_PUBLIC_ENDPOINT` deve essere raggiungibile dal browser, mentre
`MINIO_ENDPOINT` resta l'indirizzo interno usato dai container.
`MINIO_REGION` deve coincidere con `MINIO_SITE_REGION` del server (default
`us-east-1`): specificarla consente di firmare gli URL localmente, senza
tentare una richiesta dal container verso l'endpoint pubblico. I task Beat
configurano il lifecycle giornalmente e rimuovono di notte solo oggetti non
referenziati da oltre `MEDIA_ORPHAN_GRACE_HOURS`.

## 8. Retention e backup

Dettagli completi in `docs/DATABASE.md` (§ 5-7). In sintesi:

- **Retention**: un task Celery Beat notturno
  (`app.workers.tasks_maintenance.cleanup_expired_data`) cancella
  `audit_log`/`scrape_errors` più vecchi delle soglie configurate
  (`AUDIT_LOG_RETENTION_DAYS`, `SCRAPE_ERROR_RETENTION_DAYS` in `.env`) e
  libera i pacchetti di export scaduti (`EXPORT_RETENTION_DAYS`). Per
  testarlo manualmente senza aspettare le 3:00 UTC:
  ```bash
  docker compose exec worker-scraper celery -A app.workers.celery_app \
      call app.workers.tasks_maintenance.cleanup_expired_data
  ```
- **Backup**: due servizi sempre attivi nel `docker-compose.yml`,
  `backup-postgres` (dump giornalieri compressi, rotazione
  `BACKUP_RETENTION_DAYS`) e `backup-minio` (replica continua del bucket
  media). Nessuna azione manuale richiesta per farli funzionare; per
  forzare un run immediato (utile in test):
  ```bash
  docker compose exec backup-postgres sh /scripts/backup-postgres.sh --once
  docker compose exec backup-minio sh /scripts/backup-minio.sh --once
  ```
- **Ripristino** (solo manuale, mai automatico):
  ```bash
  docker compose exec backup-postgres ls -la /backups
  docker compose exec backup-postgres sh /scripts/restore-postgres.sh \
      /backups/lavoro_esterno_<timestamp>.sql.gz
  ```

## Verifiche sicurezza

```bash
cd backend
uv run bandit -r app -ll -ii
uv run pip-audit

cd ../frontend
npm audit --audit-level=high
```

Il workflow `.github/workflows/security.yml` aggiunge dependency review,
Trivy su repository/immagini e ZAP baseline/OpenAPI su stack effimero.
High/Critical bloccano la CI; le scansioni ZAP complete girano su schedule
o avvio manuale e pubblicano i report come artifact.

## 9. Observability

Prometheus raccoglie API, Celery, PostgreSQL, Redis, spazio dei volumi, Loki e
Alloy ogni 15 secondi. Le dashboard e le regole sono versionate in
`infra/grafana/provisioning`; non vanno create manualmente dalla UI, perché una
modifica manuale verrebbe sostituita dal provisioning.

Il Celery exporter resta alla versione applicativa 0.12.2, costruita dal commit
`d45a395e` con archivio verificato tramite SHA-256: rispetto alla vecchia image
Docker Hub espone anche `celery_task_queue_wait_time`, usata dalla dashboard.
Alloy assegna ai log le label stabili `compose_project`, `service`, `container`
e `stream=docker`; stdout e stderr sono letti dalla stessa API log Docker.

Alloy seleziona i container tramite la label Compose del progetto. Il default
è `lavoro-esterno-1`; se lo stack viene avviato, ad esempio, con
`docker compose -p staging up`, impostare nello stesso ambiente:

```dotenv
OBSERVABILITY_COMPOSE_PROJECT=staging
```

Il mount read-only di `/var/run/docker.sock` non consente ad Alloy di
modificare direttamente i file dell'host, ma l'API Docker resta un'interfaccia
privilegiata. In produzione limitare l'accesso al container Alloy e non
pubblicare la sua porta.

Diagnostica rapida:

```bash
# Stato dei target e regole Prometheus
curl http://localhost:9090/api/v1/targets
curl http://localhost:9090/api/v1/rules

# Metriche API dall'interno della rete Docker
docker compose exec prometheus wget -qO- http://api:8000/metrics

# Verifica raccolta log e servizi di osservabilità
docker compose logs --tail=50 alloy loki prometheus grafana
docker compose ps celery-exporter postgres-exporter redis-exporter volume-exporter
```

Gli alert bilanciati scattano per API down (2 minuti), coda oltre 100 task
(10 minuti), coda non vuota senza avanzamento (15 minuti), tre fallimenti
scraping consecutivi e spazio libero PostgreSQL/MinIO sotto il 15% (15
minuti). Non è configurato alcun contact point esterno: gli stati firing e
resolved sono consultabili nella sezione Alerting di Grafana.

La retention Loki è di 90 giorni (`2160h`), coerente con
`TECHNICAL_LOG_RETENTION_DAYS`. I dati Prometheus e le posizioni Alloy vivono
nei volumi `prometheus-data` e `alloy-data`; non usare `docker compose down
-v`, che eliminerebbe anche questi dati oltre ai volumi applicativi.
