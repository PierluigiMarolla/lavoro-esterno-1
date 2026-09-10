# Lavoro Esterno

L’interfaccia e i messaggi applicativi sono in italiano. Gli orari sono
visualizzati in `Europe/Rome` e i valori numerici con locale `it-IT`; API,
route e identificatori tecnici restano invariati per compatibilità.

Web app ad accesso riservato per raccogliere annunci da più fonti,
deduplicarli per numero di telefono, arricchirli con classificazione
automatica dei media e riepiloghi generati da AI, e permetterne la
ricerca e l'esportazione controllata.

Stack: React + Vite + TypeScript + Tailwind (frontend), FastAPI su
Python 3.13 con SQLAlchemy 2/Alembic (backend), worker Celery dedicati
per coda (`scraping`, `maintenance`, `media`, `ai`, `exports`) più uno scheduler (Celery Beat),
PostgreSQL 17, Redis, MinIO (storage media S3-compatible), Nginx come
reverse proxy, Prometheus/Grafana/Loki per l'osservabilità.

L'osservabilità include tre dashboard provisionate (API, worker Celery e
scraping per fonte), alert Grafana, exporter PostgreSQL/Redis/Celery/volumi e
raccolta dei log Docker tramite Grafana Alloy verso Loki. `/metrics` resta
interno alla rete Docker e non viene pubblicato da nginx.

## Documentazione

- [`docs/ARCHITETTURA.md`](docs/ARCHITETTURA.md) - componenti del
  sistema, flusso dati completo (scraping -> deduplicazione ->
  selezione canonica -> media -> AI -> export), ruolo di ogni servizio
  Docker.
- [`docs/API.md`](docs/API.md) - endpoint principali per area
  funzionale, esempi di flusso login+2FA ed export.
- [`docs/DATABASE.md`](docs/DATABASE.md) - schema delle tabelle
  principali e motivazioni di design (in particolare la cifratura del
  numero di telefono).
- [`docs/SICUREZZA.md`](docs/SICUREZZA.md) - autenticazione JWT, 2FA
  TOTP, RBAC, gestione segreti, cifratura, audit log, note GDPR.
- [`docs/SVILUPPO.md`](docs/SVILUPPO.md) - guida pratica per
  sviluppatori (avvio ambiente, migrazioni, test, come aggiungere un
  nuovo scraper/fonte).
- [`PROGETTO.md`](PROGETTO.md) - checklist esaustiva di tutto ciò che
  resta da fare per portare il sistema in produzione.

## Avvio rapido

Prerequisiti: Docker + Docker Compose.

```bash
cp .env.example .env
# Generare le chiavi richieste (vedi commenti in .env.example e
# docs/SVILUPPO.md per il dettaglio), poi valorizzarle in .env:
openssl rand -base64 32   # PHONE_ENCRYPTION_KEY
openssl rand -base64 32   # PHONE_HMAC_SECRET
openssl rand -base64 64   # JWT_SECRET_KEY
openssl rand -base64 32   # PROXY_CREDENTIAL_ENCRYPTION_KEY (se necessaria)

docker compose up --build

# Il DB parte vuoto: applicare le migrazioni...
docker compose exec api alembic upgrade head

# ...creare il primo utente Admin (nessun endpoint API può farlo)
docker compose exec api python -m app.scripts.create_admin --email admin@lavoro.internal --password "una-password-forte"

# ...e creare le fonti da acquisire via API/UI (form "Aggiungi fonte" nella
# pagina Fonti, o POST /sources) — vedi docs/SVILUPPO.md § 5
```

Le modalità browser vengono incluse nell'immagine backend: Chromium è usato
normalmente, mentre l'opzione Sources “Chrome reale” usa Google Chrome tramite
Patchright. Se un'immagine precedente segnala che `/opt/google/chrome/chrome`
non esiste, ricostruire `api` e `worker-scraper` con `--build`.

Applicazione raggiungibile su `http://localhost/` (reverse proxy nginx),
documentazione API interattiva su `http://localhost/docs`. Sequenza
verificata su un ambiente Docker reale in questa sessione di sviluppo.

Su Docker Desktop/Windows, se `localhost` resta in attesa mentre
`http://127.0.0.1` funziona, eseguire prima la diagnosi non distruttiva:

```powershell
.\scripts\windows\Repair-Localhost.ps1
```

Lo script indica se `[::1]:80` è occupato da un relay WSL non responsivo e
spiega come avviare la riparazione verificata da PowerShell elevata. Non
arresta processi in modalità diagnostica e non elimina volumi Docker.

Per il dettaglio di ogni comando (migrazioni Alembic, test, sviluppo
frontend con hot reload) vedi [`docs/SVILUPPO.md`](docs/SVILUPPO.md).

## Struttura del repository

```
.
├── docker-compose.yml       # Definizione di tutti i servizi dello stack
├── .env.example              # Variabili d'ambiente richieste (template)
├── PROGETTO.md                # Checklist verso la produzione
├── docs/                      # Documentazione tecnica
│   ├── ARCHITETTURA.md
│   ├── API.md
│   ├── DATABASE.md
│   ├── SICUREZZA.md
│   └── SVILUPPO.md
├── infra/                     # Configurazioni di infrastruttura
│   ├── nginx/nginx.conf
│   ├── prometheus/prometheus.yml
│   ├── grafana/provisioning/
│   ├── loki/loki-config.yml
│   ├── alloy/config.alloy
│   └── backup/                # Script backup/restore Postgres + MinIO
├── .github/workflows/ci.yml   # Pipeline CI (lint, test, build immagini)
├── backend/                   # API FastAPI, worker Celery, migrazioni Alembic
└── frontend/                  # SPA React + Vite + TypeScript
```

## Stato del progetto

L'infrastruttura e i flussi principali sono implementati, inclusi scraper
generici con proxy rotator e schedulazione fixed-delay per fonte (il timer
riparte soltanto dalla conclusione dello scan precedente), pipeline media
ONNX/FFmpeg, riepiloghi AI multiprovider, export e flussi GDPR. Restano i gate
di produzione e la validazione esterna. Vedi
[`PROGETTO.md`](PROGETTO.md) per l'elenco dettagliato del lavoro
rimanente.

Le fonti possono essere duplicate dalla UI Admin copiando tutta la
configurazione ma non lo storico; la copia nasce disabilitata. Admin e Operator
possono riabilitare dalla stessa tabella fonti disabilitate o in pausa.
