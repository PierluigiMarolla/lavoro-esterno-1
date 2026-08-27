# Riassunto sessione - Progetto "Lavoro Esterno"

Questo file riassume cosa è stato fatto in questa conversazione, per poter
proseguire il lavoro in una conversazione/sessione diversa senza perdere
contesto. Data sessione: 27 agosto 2026.

## Richiesta originale

L'utente ha fornito un PDF (`lavoro-esterno-1-stack-tecnico.pdf`, in root)
con lo stack tecnico e l'architettura di un sistema web riservato per:
raccogliere annunci da più siti/fonti, normalizzarli, deduplicarli usando
il numero di telefono come chiave funzionale di raggruppamento, gestire
media con classificazione contenuti espliciti/non espliciti, generare
riepiloghi AI, ed esportare dati/media in modalità controllate.

La cartella `desing/` (nome scritto così, con refuso, non rinominare senza
motivo) contiene 8 mockup HTML statici con Tailwind via CDN + uno
`screen.png` ciascuno, più un `DESIGN.md` con i design token: login,
dashboard, admin, search, sources, exports, e le 5 tab della pagina
record detail (overview, occurrences, media, history, ai_summary).

L'utente ha chiesto di:
1. Creare il progetto completo descritto nel PDF, seguendo fedelmente i
   design in `desing/` per il frontend.
2. Preparare un file `.md` con tutti i punti necessari per completare il
   progetto (→ è diventato `PROGETTO.md`).
3. Fare tutte le domande necessarie prima di procedere (sessione partita
   in **plan mode**).

## Decisioni prese con l'utente (via AskUserQuestion)

- **Scope**: scaffold COMPLETO di tutto lo stack (frontend + backend + DB +
  worker + storage + observability + docker compose + CI), non solo una
  parte.
- **Scraper per fonte** (escort_advisor, bakeca_incontri, moscarossa,
  megaescort, escortforumit, escortacom, rosa_rossa, torino_erotica,
  punterforum): solo classe base + stub, NESSUNO scraping reale in questa
  fase.
- **AI/classificazione media**: solo interfaccia intercambiabile con
  implementazione di default a regole semplici/mock (placeholder), pronta
  per essere sostituita da ONNX/LLM reali in futuro.
- **Ambiente**: tutto locale da zero via Docker Compose, nessuna infra
  preesistente.
- **Niente Keycloak**: autenticazione gestita interamente da FastAPI con
  JWT. Richiesto un **alto livello di sicurezza con 2FA obbligatoria**
  (per il ruolo Admin) → scelto **TOTP** (Google/Microsoft Authenticator,
  libreria `pyotp`), non email OTP.
- **Observability** (Prometheus/Grafana/Loki): inclusa nel docker-compose
  fin da subito, non rimandata.
- **Package manager**: `uv` per Python, `npm` per il frontend TypeScript.
- **Requisito aggiunto in corso d'opera**: il codice deve essere BEN
  COMMENTATO e va prodotta documentazione tecnica dettagliata separata dal
  codice (cartella `docs/`), non solo `PROGETTO.md`.

Il piano finale approvato è salvato (fuori dal repo) in:
`C:\Users\pierl\.claude\plans\in-questa-cartella-crea-cuddly-jellyfish.md`

## Cosa è stato costruito

Il lavoro è stato eseguito con **3 agenti in parallelo** (backend,
frontend, infra/docs/PROGETTO.md), seguito da un giro di verifica manuale
di coerenza e da un **4° agente di riconciliazione** per allineare gli
endpoint backend al contratto atteso dal frontend, seguito da correzioni
manuali finali.

### `backend/` (Python 3.13, FastAPI)

- `app/models/` — 12 tabelle SQLAlchemy 2 con enum PostgreSQL nativi:
  `record`, `advertisement`, `media`, `sources`, `canonical_history`,
  `scrape_runs`, `scrape_errors`, `media_classification_history`,
  `summary_versions`, `export_jobs`, `audit_log`, `users`.
- `app/services/`:
  - `phone_crypto.py` — normalizzazione telefono, cifratura AES-256-GCM
    (`PHONE_ENCRYPTION_KEY`) + hash di lookup HMAC-SHA256
    (`PHONE_HMAC_SECRET`): il telefono non è mai la chiave primaria in
    chiaro.
  - `dedup.py` — dedup multilivello (telefono/URL/SHA-256 reali, resto con
    TODO).
  - `canonical.py` — regola deterministica di selezione canonica (priorità
    bakeca_incontri, poi tie-break su campi validi/priorità fonte).
  - `media_classifier.py`, `summary_generator.py` — interfacce con
    implementazione placeholder chiaramente documentata.
- `app/scrapers/` — ABC `Scraper` + 9 stub (uno per fonte) + `registry.py`.
- `app/security/` — JWT (`jwt.py`), password argon2 (`password.py`), TOTP
  con QR code e backup codes (`totp.py`), dependency RBAC (`deps.py`).
- `app/workers/` — Celery con code `scraping`/`media`/`ai` +
  `celery_app.py`.
- `app/api/v1/` — router `auth`, `dashboard`, `records`, `sources`,
  `exports`, `admin`, `media`, tutti collegati realmente al DB.
- `migrations/` — Alembic (env.py async) con la migrazione iniziale
  completa.
- `tests/` — 54 test pytest, tutti passanti (verificato più volte in
  questa sessione).

### `frontend/` (React 18 + Vite + TypeScript + Tailwind)

- Design token replicati esattamente da `desing/lavoro_esterno_core/
  DESIGN.md` in `tailwind.config.ts`.
- Layout condiviso (`Sidebar`, `Topbar`, `AppShell`) fedele ai mockup
  admin/dashboard.
- Tutte le route: `/login` (con step 2FA), `/dashboard`, `/search`,
  `/records/:id` (con 5 tab), `/sources`, `/exports`, `/admin`.
- `src/api/*.ts` — client tipizzato verso il backend, con refresh
  automatico del token su 401 (`src/api/client.ts`).
- Componenti UI riutilizzabili in stile shadcn (`src/components/ui/`).
- Nessun dato hardcoded: tutte le pagine usano hook TanStack Query reali.

### Root del repo

- `docker-compose.yml` — 13 servizi (postgres, redis, minio, api,
  worker-scraper, worker-media, worker-ai, scheduler, frontend, nginx,
  prometheus, grafana, loki).
- `.env.example`, `.gitignore`, `.github/workflows/ci.yml`.
- `docs/ARCHITETTURA.md`, `docs/API.md`, `docs/DATABASE.md`,
  `docs/SICUREZZA.md`, `docs/SVILUPPO.md` — documentazione tecnica
  dettagliata specifica del progetto.
- `PROGETTO.md` — checklist esaustiva di tutto ciò che resta da fare
  (scraper reali per fonte, AI/classificazione reale, export reali,
  dashboard Grafana, GDPR/legale, deploy produzione, ecc.). **Consultare
  questo file per sapere cosa manca**, in particolare la sezione
  "11. Note di compromesso su questa consegna" che elenca i problemi di
  coerenza trovati e già corretti.
- `README.md` — quick start con `docker compose up --build`.

## Problemi di coerenza trovati e corretti in questa sessione

Poiché backend, frontend e infrastruttura sono stati creati da agenti
diversi senza vedersi, sono stati necessari due giri di verifica/fix
manuali (dettagliati anche in `PROGETTO.md`):

1. **Giro 1 (infrastruttura)**: comando Celery in `docker-compose.yml`
   puntava a un modulo Python inesistente (`app.worker` invece di
   `app.workers.celery_app`); variabili in `.env.example` con nomi diversi
   da quelli letti da `backend/app/config.py` (es. `MINIO_USE_SSL` vs
   `MINIO_SECURE`, `JWT_REFRESH_SECRET_KEY` inesistente lato backend);
   `VITE_API_URL` non passato come build-arg al frontend (Vite lo "bake-a"
   a build time, non runtime); CI con `uv sync --frozen` senza `uv.lock`
   committato; `.gitignore` root mancante.

2. **Giro 2 (contratto API backend↔frontend)**: il backend inizialmente
   implementava solo una manciata di endpoint minimi, mentre il frontend
   (costruito sui mockup) si aspettava un'API molto più ricca. Un agente
   dedicato ha esteso il backend per implementare: `GET /dashboard/kpis`,
   `/scraping-activity`, `/source-health`, `/activity`; `GET /records/
   search` (paginato), `/{id}/occurrences`, `/media`, `/history`,
   `/ai-summary` (+ regenerate); `GET /sources/summary`, `POST /sources/
   {id}/pause|disable`; `GET /exports`, `POST /exports/{id}/retry`,
   `GET /exports/{id}/download`; `PATCH /admin/users/{id}`, `POST /admin/
   users/{id}/suspend`, `GET /admin/audit-log`; `POST /auth/logout`.

3. **Giro 3 (fix manuali finali, dopo il giro 2)**: verificando a mano ho
   trovato altri due mismatch critici sfuggiti al giro 2, entrambi
   bloccanti per l'uso base dell'app, e li ho corretti io stesso:
   - Login (`POST /auth/login`, `/auth/login-2fa`, `GET /auth/me`)
     rispondeva con `requires_2fa`/`login_ticket` e senza oggetto `user`,
     mentre il frontend si aspettava `status`/`mfa_token` e un `user`
     completo (`id/email/name/role/mfaEnabled/status`). Corretto in
     `backend/app/schemas/auth.py` (nuova classe `UserPublic`) e
     `backend/app/api/v1/auth.py`. Nota: `user.name` e `user.status` sono
     **derivati** (email/`is_active`), non hanno colonne dedicate nel
     modello `User` — placeholder documentato.
   - `GET /sources` rispondeva con la forma grezza del modello SQLAlchemy
     (snake_case, `slug`/`base_url`/`priority`) invece di
     `code`/`country`/`lastRunAt`/`itemsLast24h`/`errorRate` in camelCase.
     Corretto in `backend/app/schemas/sources.py` (ora eredita da
     `CamelModel`) e `backend/app/api/v1/sources.py` (calcolo aggregato
     da `scrape_runs` per fonte, con approssimazione N+1 documentata e
     accettata per il volume di fonti atteso). `country` resta un
     placeholder fisso `"N/D"` (nessun campo geografico nel modello).

   Dopo ogni correzione ho verificato: `python -m py_compile`, import
   completo di `app.main` (41 route registrate), suite pytest completa
   (54/54 passati).

## Aggiornamento: build reale eseguita e bug corretti (stesso giorno)

In una seconda parte della sessione l'utente ha eseguito `docker compose
up --build` sulla sua macchina e ha incontrato un errore (`npm install`
falliva con `ERESOLVE`). Da lì è partito un giro di verifica **end-to-end
reale** (Docker disponibile in quell'ambiente), che ha trovato e corretto
diversi bug non rilevabili da compilazione/test statici:

- `eslint-plugin-react-hooks` incompatibile con ESLint 9 → aggiornato a
  `^5.0.0`.
- `npm run build` falliva (TS): mancava `frontend/src/vite-env.d.ts`,
  `tsconfig.node.json` senza `@types/node`, un import inutilizzato.
- `eslint.config.js` disabilitava erroneamente `no-undef` sui tipi DOM
  ambientali TS.
- `backend/pyproject.toml` dichiarava un `readme = "README.md"`
  inesistente → `pip install -e .` falliva nel Dockerfile. Rimosso.
- **Migrazione Alembic rotta**: gli enum Postgres venivano creati due
  volte (`DuplicateObjectError`) per mancanza di `create_type=False`.
  Corretto in `backend/migrations/versions/20260827120000_initial_schema.py`.
- **Bootstrap impossibile**: nessun modo di creare il primo utente Admin
  (l'unico endpoint di creazione utenti richiede già un Admin con 2FA).
  Aggiunto `backend/app/scripts/create_admin.py`.
- `GET /sources` e `GET /exports` rispondevano 307 (redirect per slash
  finale mancante) quando chiamati come fa il frontend → route corrette
  da `@router.get("/")` a `@router.get("")`.
- `docs/SVILUPPO.md` conteneva istruzioni inventate/non allineate al
  codice reale (metodi scraper, campi `sources`, endpoint inesistenti) →
  riscritto per riflettere il codice reale.
- **`loki` in crash-loop** (`CONFIG ERROR: compactor.delete-request-store
  should be configured when retention is enabled`): corretto aggiungendo
  `delete_request_store: filesystem` in `infra/loki/loki-config.yml`.

**Tutto questo è stato verificato dal vivo**, non solo in teoria: build
di tutte le immagini Docker, avvio dei 13 servizi, migrazioni applicate
su Postgres reale, creazione di un utente Admin, login riuscito con la
forma di risposta esatta attesa dal frontend, ed endpoint chiave
(`/auth/me`, `/sources`, `/sources/summary`, `/exports`, `/dashboard/
kpis`, `/admin/users`) tutti raggiungibili con 200 tramite il reverse
proxy nginx. Dettagli completi in `PROGETTO.md`, sezione 12.

## Cosa NON è ancora stato verificato

- **Navigazione manuale della UI in un browser reale**: solo l'API è
  stata esercitata via `curl`, non l'interfaccia React nel browser.
- **Flusso 2FA completo** (setup QR code, verifica, login con codice
  TOTP): il login testato è stato quello senza 2FA attiva.
- **`package-lock.json`/`uv.lock`**: il primo è stato generato durante
  questa sessione (`npm install` eseguito con successo); `uv.lock` per il
  backend NON è ancora stato generato (il backend è stato verificato con
  `pip install` dentro Docker, non con `uv`).
- Possibili altri micro-disallineamenti di contratto API potrebbero
  emergere solo navigando pagine non ancora esercitate manualmente (es.
  tab dettaglio record, pagina export con job reali).
- Nessuna validazione legale/GDPR, nessuno scraper reale, nessun
  classificatore AI reale, nessuna dashboard Grafana configurata.

## Prossimi passi consigliati (in ordine)

1. `docker compose up --build` (ora funziona), poi `docker compose exec
   api alembic upgrade head`, poi creare l'Admin con
   `docker compose exec api python -m app.scripts.create_admin --email
   ... --password ...` (vedi `README.md` per i dettagli).
2. Login nel browser su `http://localhost/`, navigare tutte le pagine e
   confrontarle visivamente con `desing/*/screen.png`.
3. Abilitare la 2FA sull'utente Admin appena creato e verificare il
   flusso completo (mai testato finora).
4. Generare `backend/uv.lock` eseguendo `uv sync` in locale (il backend
   finora è stato verificato solo con `pip`, coerente con le dipendenze
   in `pyproject.toml` ma non ancora con `uv` in prima persona).
5. Consultare `PROGETTO.md` per la checklist completa di lavoro rimanente
   (scraper reali, classificatore AI reale, generazione export reale,
   dashboard Grafana, deploy produzione).

## File chiave da leggere per ripartire

- `PROGETTO.md` (root) — checklist e note di compromesso.
- `docs/ARCHITETTURA.md`, `docs/API.md`, `docs/DATABASE.md`,
  `docs/SICUREZZA.md`, `docs/SVILUPPO.md` — documentazione tecnica.
- `backend/app/schemas/auth.py` e `backend/app/api/v1/auth.py` — contratto
  di login/2FA, appena corretto.
- `backend/app/schemas/sources.py` e `backend/app/api/v1/sources.py` —
  contratto fonti, appena corretto.
- `frontend/src/types/index.ts` — fonte di verità per la forma dei dati
  attesi da tutto il frontend.
