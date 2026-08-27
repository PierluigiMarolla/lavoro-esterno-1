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
openssl rand -base64 64   # -> JWT_SECRET_KEY
openssl rand -base64 64   # -> JWT_REFRESH_SECRET_KEY
# Incollare i valori generati nel file .env (mai committarlo)

# 3. Costruire e avviare l'intero stack
docker compose up --build
```

Servizi raggiungibili dopo l'avvio:

- Frontend/API tramite reverse proxy: `http://localhost/`
- Documentazione API interattiva: `http://localhost/docs`
- Console MinIO: `http://localhost:9001`
- Grafana: `http://localhost:3000` (utente `admin`, password da
  `GF_SECURITY_ADMIN_PASSWORD`)
- Prometheus: `http://localhost:9090`

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
uv sync --all-extras
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

## 5. Aggiungere un nuovo connettore scraper

Ogni fonte (sito di annunci) ha un connettore scraper dedicato in
`backend/app/scrapers/`, che implementa un'interfaccia comune definita in
**`backend/app/scrapers/base.py`**. Passi per aggiungerne uno nuovo:

1. Creare il modulo del connettore, es.
   `backend/app/scrapers/<nome_fonte>.py`, con una classe che eredita
   dalla classe base astratta di `base.py` (metodi tipici attesi:
   `list_advertisement_urls()` per elencare gli annunci disponibili,
   `parse_advertisement(html)` per estrarre i campi normalizzati,
   gestione paginazione e rate limiting).
2. Registrare il connettore nel **registry degli scraper** (mappa
   `source_code -> classe connettore`, usata dal task Celery generico
   sulla coda `scraping` per instanziare il connettore giusto in base al
   campo `sources.code`).
3. Implementare l'estrazione e normalizzazione dei campi richiesti:
   titolo, descrizione, città, età dichiarata, numero di telefono (che
   verrà normalizzato in E.164 e poi cifrato/hashato dal layer comune,
   il connettore non deve gestire la cifratura), URL media.
4. Rispettare rate limiting/backoff configurati per la fonte
   (`sources.rate_limit_config`) per non sovraccaricare il sito di
   origine.
5. Gestire e propagare gli errori in modo che vengano registrati in
   `scrape_errors` (non silenziarli: un run parzialmente fallito deve
   risultare visibile in `scrape_runs.status = partial_failure`).
6. Scrivere test unitari per il parsing (HTML di esempio salvato come
   fixture, non richieste live verso il sito reale nei test automatici).
7. **Prima di attivare il connettore in produzione**: verificare
   `robots.txt` e termini di servizio della fonte, aggiornare
   `sources.robots_txt_checked_at`/`tos_notes` (vedi `docs/SICUREZZA.md`,
   §7, e la checklist per-fonte in `PROGETTO.md`).

## 6. Aggiungere una nuova fonte in `sources`

Una "fonte" (riga in `sources`, vedi `docs/DATABASE.md`) è distinta dal
connettore scraper: il connettore è codice, la fonte è configurazione.

1. Assicurarsi che esista il connettore scraper corrispondente (punto 5
   sopra) e conoscerne il `code` univoco usato per la registrazione.
2. Inserire la fonte, tipicamente via endpoint amministrativo
   `POST /api/v1/sources` (solo ruolo Admin, vedi `docs/API.md`) o via
   seed/migrazione dati per gli ambienti di sviluppo, con almeno:
   `code`, `display_name`, `base_url`, `is_active`, `scrape_schedule_
   cron`, `rate_limit_config`.
3. Verificare che lo scheduler (Celery Beat) prenda in carico la nuova
   pianificazione dopo il riavvio/reload della configurazione.
4. Eseguire un run manuale di test
   (`POST /api/v1/sources/{source_id}/runs`) e controllare `scrape_runs`
   / `scrape_errors` prima di lasciare la fonte attiva in produzione.
