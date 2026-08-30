# Lavoro Esterno

Web app ad accesso riservato per raccogliere annunci da più fonti,
deduplicarli per numero di telefono, arricchirli con classificazione
automatica dei media e riepiloghi generati da AI, e permetterne la
ricerca e l'esportazione controllata.

Stack: React + Vite + TypeScript + Tailwind (frontend), FastAPI su
Python 3.13 con SQLAlchemy 2/Alembic (backend), worker Celery dedicati
per coda (`scraping`, `media`, `ai`) più uno scheduler (Celery Beat),
PostgreSQL 17, Redis, MinIO (storage media S3-compatible), Nginx come
reverse proxy, Prometheus/Grafana/Loki per l'osservabilità.

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

docker compose up --build

# Il DB parte vuoto: applicare le migrazioni...
docker compose exec api alembic upgrade head

# ...creare il primo utente Admin (nessun endpoint API può farlo)
docker compose exec api python -m app.scripts.create_admin \
    --email admin@lavoro.internal --password "una-password-forte"

# ...e creare le fonti da scrapare via API/UI (form "Add Source" nella
# pagina Sources, o POST /sources) — vedi docs/SVILUPPO.md § 5
```

Applicazione raggiungibile su `http://localhost/` (reverse proxy nginx),
documentazione API interattiva su `http://localhost/docs`. Sequenza
verificata su un ambiente Docker reale in questa sessione di sviluppo.

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
│   └── backup/                # Script backup/restore Postgres + MinIO
├── .github/workflows/ci.yml   # Pipeline CI (lint, test, build immagini)
├── backend/                   # API FastAPI, worker Celery, migrazioni Alembic
└── frontend/                  # SPA React + Vite + TypeScript
```

## Stato del progetto

Repository in fase di bootstrap: infrastruttura, documentazione e CI
sono definite; l'implementazione applicativa (connettori scraper reali,
classificazione AI, generazione export) è in corso. Vedi
[`PROGETTO.md`](PROGETTO.md) per l'elenco dettagliato del lavoro
rimanente.
