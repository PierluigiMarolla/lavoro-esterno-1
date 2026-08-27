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
```

Questa intera sequenza (`docker compose up --build`, migrazioni, creazione
admin, login) è stata eseguita ed è stata verificata contro un ambiente
Docker reale: build delle 6 immagini custom, avvio dei 13 servizi, `POST
/api/v1/auth/login` funzionante con la coppia access/refresh token e
l'oggetto `user` atteso dal frontend.

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

## 5. Aggiungere un nuovo connettore scraper

Ogni fonte (sito di annunci) ha un connettore scraper dedicato in
`backend/app/scrapers/`, che implementa un'interfaccia comune definita in
**`backend/app/scrapers/base.py`**. Passi per aggiungerne uno nuovo:

1. Creare il modulo del connettore, es.
   `backend/app/scrapers/<slug_fonte>.py`, con una classe che eredita da
   `Scraper` (`backend/app/scrapers/base.py`) e imposta `slug`/`base_url`.
   I 4 metodi astratti da implementare sono `async discover(self) ->
   list[str]` (elenca gli URL dei singoli annunci), `async scrape_ad(self,
   url) -> dict` (scarica ed estrae i dati grezzi di un annuncio), `async
   download_media(self, ad)` e `async normalize(self, data)` (mappa i
   campi grezzi sul formato comune usato da `app/services/dedup.py` e
   `canonical.py`). Gli stub esistenti (es.
   `backend/app/scrapers/bakeca_incontri.py`) sollevano
   `NotImplementedError` con un messaggio che ricorda di rispettare ToS e
   rate limit: da sostituire con l'implementazione reale.
2. Registrare il connettore in `backend/app/scrapers/registry.py` (mappa
   `slug -> classe connettore`).
3. Il numero di telefono estratto va passato così com'è (stringa grezza)
   al layer comune: la normalizzazione E.164, la cifratura AES-256-GCM e
   l'hash di lookup HMAC-SHA256 sono responsabilità di
   `app/services/phone_crypto.py`, il connettore non deve gestirle.
4. Rispettare `rate_limit_seconds` (attributo di classe su `Scraper`,
   sovrascrivibile per fonte) per non sovraccaricare il sito di origine.
5. Gestire e propagare gli errori in modo che vengano registrati in
   `scrape_errors` (collegati a `scrape_runs`), non silenziarli.
6. Scrivere test unitari per il parsing (HTML di esempio salvato come
   fixture, non richieste live verso il sito reale nei test automatici).
7. **Prima di attivare il connettore in produzione**: verificare
   `robots.txt` e termini di servizio della fonte (vedi
   `docs/SICUREZZA.md` e la checklist per-fonte in `PROGETTO.md`). Il
   modello `Source` non ha oggi colonne dedicate per tracciare questa
   verifica (`robots_txt_checked_at`, ecc.): è un'estensione di schema da
   valutare quando si passa a scraper reali, non ancora presente.

## 6. Aggiungere una nuova fonte in `sources`

Una "fonte" (riga in `sources`, vedi `docs/DATABASE.md`: `name`, `slug`,
`base_url`, `priority`, `status`, `enabled`) è distinta dal connettore
scraper: il connettore è codice, la fonte è configurazione runtime.

1. Assicurarsi che esista il connettore scraper corrispondente (punto 5
   sopra) e conoscerne lo `slug` univoco usato per la registrazione.
2. Inserire la riga in `sources` (oggi non esiste un endpoint `POST
   /api/v1/sources` nel backend, solo `GET /sources`, `GET
   /sources/summary`, `POST /sources/{id}/scan|pause|disable` — vedi
   `docs/API.md`): per gli ambienti di sviluppo, inserirla direttamente
   via SQL/script oppure aggiungere l'endpoint di creazione mancante,
   annotato in `PROGETTO.md`.
3. Eseguire un run manuale di test con `POST
   /api/v1/sources/{source_id}/scan` (accoda un task sulla coda
   `scraping`, vedi `backend/app/workers/tasks_scraper.py`) e controllare
   `scrape_runs`/`scrape_errors` prima di lasciare la fonte attiva.
