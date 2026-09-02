# Riassunto sessione - Progetto "Lavoro Esterno"

Questo file riassume cosa è stato fatto in questa conversazione, per poter
proseguire il lavoro in una conversazione/sessione diversa senza perdere
contesto. Data sessione: 27 agosto 2026.

> **Nota**: esiste una sessione successiva (28 agosto 2026) che ha
> completato la sezione "1. Autenticazione / 2FA" di `PROGETTO.md` per
> intero. Il suo riassunto è in fondo a questo file, sezione
> **"Sessione 2 — 28 agosto 2026"**: chi riprende il lavoro dovrebbe
> leggere prima quella (più recente), poi tornare qui per il contesto
> originale del progetto se necessario.

> **Aggiornamento più recente**: la sessione del **1 settembre 2026** ha
> completato i punti 5 e 6 di `PROGETTO.md` (AI/classificazione e pipeline
> storage/media). Il riepilogo operativo aggiornato si trova in fondo al
> file, sezione **"Sessione 5 — 1 settembre 2026"**, che va letta per prima
> quando si riprende il progetto.

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
- `app/scrapers/` — ABC `Scraper` + `GenericScraper` (motore generico
  configurabile via `Source.scrape_config`, basato su Scrapling con
  `fetchMode` HTTP/dynamic/stealth). I 9 stub per-fonte iniziali e il
  `registry.py` che li risolveva sono stati rimossi in un secondo momento:
  ogni fonte va configurata dall'operatore tramite il motore generico,
  nessun connettore per-sito precompilato.
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

---

# Sessione 2 — 28 agosto 2026

## Richiesta

Partendo da `PROGETTO.md` (checklist creata nella sessione 1), l'utente ha
chiesto di:
1. Esaminare l'intero progetto e spuntare in `PROGETTO.md` le task già
   completate (fatto: solo "migrazioni Alembic iniziali" in sezione 2 era
   effettivamente completo, tutto il resto ancora da fare).
2. Completare **per intero** la sezione "1. Autenticazione / 2FA" di
   `PROGETTO.md` (6 task), garantendo che tutto funzioni al 100%, con
   verifica reale (non solo teorica).

Sessione partita in **plan mode**; piano approvato salvato (fuori dal
repo) in `C:\Users\playn\.claude\plans\ora-sempre-tenendo-in-elegant-stream.md`.

## Decisioni prodotto prese con l'utente (via AskUserQuestion)

- **MFA per il ruolo Operator: obbligatoria da subito** (stesso livello
  di Admin, nessun periodo di grazia).
- **Password policy: solo complessità minima, nessuna scadenza forzata.**
- Recovery account: dato che non esiste alcun servizio email nel
  progetto, si è scelto un meccanismo **admin-driven** (reset 2FA da
  parte di un Admin), non un flusso self-service via email.

## Cosa è stato implementato (tutte e 6 le task di § 1)

### Backend (Python/FastAPI)

- **`backend/app/models/users.py`**: nuova colonna `security_stamp_at`
  (timestamptz, `server_default=now()`). Nuova migrazione Alembic
  `backend/migrations/versions/20260828090000_users_security_stamp.py`.
- **`backend/app/security/jwt.py`**: ogni access/refresh token porta ora
  due claim nuovi: `jti` (id univoco, per blacklist puntuale) e `sst`
  (snapshot di `security_stamp_at` all'emissione, per revoca in blocco).
  Nuova utility `remaining_ttl_seconds`.
- **`backend/app/security/redis_client.py`** (nuovo): blacklist `jti` +
  contatori di rate limiting/lockout, tutto su Redis (già disponibile nel
  compose per Celery), chiavi con prefisso `auth:`.
- **`backend/app/security/deps.py`**: `get_current_user` ora (a) rifiuta
  token con `jti` in blacklist o `sst` non corrispondente, (b) blocca con
  403 (`error_code: mfa_setup_required`) i ruoli admin/operator privi di
  2FA attiva. Nuova `get_current_user_allow_unenrolled` per gli endpoint
  di setup stesso (`/me`, `/logout`, `/setup-2fa`, `/verify-2fa`,
  `/2fa/backup-codes/regenerate`, `/change-password`). Nessuna modifica
  necessaria negli altri router (sources/records/media/dashboard/search):
  ereditano l'enforcement automaticamente.
- **`backend/app/security/totp.py`**: nuovo `regenerate_backup_codes()`.
- **`backend/app/security/password.py`**: nuovo
  `validate_password_strength()` + `WeakPasswordError` (lunghezza minima,
  varietà classi di caratteri, denylist password comuni, non deve
  contenere l'email).
- **`backend/app/config.py`** + **`.env.example`**: nuovi settings
  `LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_MINUTES`, `MFA_MAX_ATTEMPTS`,
  `MFA_LOCKOUT_MINUTES`, `PASSWORD_MIN_LENGTH`.
- **`backend/app/api/v1/auth.py`** (riscritto): rate limiting su
  `/login`/`/login-2fa`/`/verify-2fa`; `/login` restituisce
  `status="mfa_setup_required"` per admin/operator senza 2FA; auto-rigenerazione
  backup codes sull'ultimo consumato (`new_backup_codes` in risposta);
  `/logout` blacklista i `jti` (access + refresh se inviato); `/refresh`
  verifica blacklist/`sst`; nuovi endpoint `POST /auth/2fa/backup-codes/
  regenerate` e `POST /auth/change-password` (quest'ultimo aggiorna
  `security_stamp_at`, revocando tutte le sessioni precedenti).
- **`backend/app/api/v1/admin.py`**: nuovo `POST /admin/users/{id}/
  reset-2fa` (recovery account, admin-driven).
- **`backend/app/schemas/auth.py`** e **`schemas/admin.py`**: nuovi schemi
  di richiesta/risposta; `UserCreate` ora valida la password con
  `validate_password_strength` via `model_validator`.
- **`backend/app/scripts/create_admin.py`**: valida anch'esso la password.
- Nuovi test: `backend/tests/test_password_policy.py`,
  `backend/tests/test_backup_codes.py` (65/65 pytest totali passano).

### Frontend (React/TS)

- **`frontend/src/types/index.ts`**: `UserRole` corretto da
  `"admin"|"analyst"|"viewer"` (bug pre-esistente, non combaciava mai con
  l'enum backend `"admin"|"operator"|"viewer"`) a
  `"admin"|"operator"|"viewer"`; `LoginResult` esteso con la variante
  `mfa_setup_required`. **`frontend/src/routes/AdminPage.tsx`** aggiornato
  di conseguenza (`ROLE_LABEL`).
- **`frontend/src/api/client.ts`**: emette l'evento
  `lavoro-esterno:mfa-setup-required` su 403 con quell'`error_code`.
- **`frontend/src/api/auth.ts`**: nuove funzioni `setupTwoFactor`,
  `verifyTwoFactorSetup`, `regenerateBackupCodes`, `changePassword`;
  `logout()` ora invia il refresh token nel body.
- **`frontend/src/context/AuthContext.tsx`**: nuovo
  `requiresTwoFactorSetup` (derivato da `user.role`+`mfaEnabled`), nuovo
  `completeTwoFactorSetup`.
- **`frontend/src/routes/ProtectedRoute.tsx`**: reindirizza a
  `/2fa-setup` quando `requiresTwoFactorSetup` è vero.
- **`frontend/src/routes/TwoFactorSetupPage.tsx`** (nuova pagina): QR
  code + secret + backup codes + verifica codice. Nessun mockup esiste
  per questa schermata (flusso nuovo, non nei `desing/` originali).
- **`frontend/src/routes/LoginPage.tsx`**: step MFA ora accetta anche
  backup code alfanumerici (non solo 6 cifre), redirect a
  `/2fa-setup` su `mfa_setup_required`, modale bloccante per mostrare
  `new_backup_codes` quando rigenerati automaticamente.
- **`frontend/src/App.tsx`**: nuova route `/2fa-setup`.
- `npm run build` e `npm run lint` puliti (0 errori; 1 warning
  pre-esistente identico in `AuthContext.tsx`, non introdotto ora).

## Due bug pre-esistenti trovati e corretti (bloccavano la verifica)

1. **`.env.example`**: `PHONE_ENCRYPTION_KEY=change-me-32-byte-base64-key-000000=`
   non era base64 valido → crash (`binascii.Error`) al primo utilizzo
   reale (setup 2FA, cifratura telefono). Sostituito con un placeholder
   di sviluppo valido (`MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=`),
   con commento che spiega perché deve restare base64 valido a 32 byte.
2. **Bug latente FastAPI/Pydantic**: endpoint con `-> None` e
   `status_code=204` (in questo ambiente/versioni: fastapi 0.115.6,
   pydantic 2.11.x, Python 3.13) falliscono la registrazione della route
   con `AssertionError: Status code 204 must not have a response body`,
   perché la risoluzione dell'annotazione `None` (con
   `from __future__ import annotations`) produce `NoneType` (truthy)
   invece del singleton `None`. Riguardava sia i miei nuovi endpoint
   (`/auth/logout`, `/auth/change-password`) sia due endpoint
   preesistenti mai esercitati a fondo (`POST /sources/{id}/pause` e
   `/disable`). **Corretto aggiungendo `response_model=None` esplicito**
   a tutti e 4. Da tenere a mente se si aggiungono altri endpoint 204 in
   futuro.

## Verifica end-to-end reale (Docker disponibile in questo ambiente)

`docker compose up --build` (13 servizi), `alembic upgrade head`
(applica anche la nuova migrazione `security_stamp_at`),
`create_admin.py` per il bootstrap. Poi uno script bash dedicato
(non committato, era in una cartella scratchpad temporanea) ha
verificato dal vivo, con richieste HTTP reali attraverso nginx, TUTTI e
6 i comportamenti:

1. Login Admin senza 2FA → `mfa_setup_required`; `GET /dashboard/kpis`
   → 403 prima del setup, → 200 dopo `setup-2fa`+`verify-2fa`.
2. 6 login falliti su un'email inesistente → lockout dopo la soglia,
   429 con `retry_after_seconds` persistente sui tentativi successivi.
3. Creato un utente Operator, completato il suo setup 2FA, consumati
   tutti e 10 i backup code via `login-2fa`: sul decimo,
   `new_backup_codes` è arrivato popolato con 10 codici nuovi; il primo
   codice (ormai consumato) è stato correttamente rifiutato (401) se
   riusato.
4. `POST /admin/users/{id}/reset-2fa` sull'Operator → al login
   successivo, di nuovo `mfa_setup_required` (recovery funzionante).
5. `POST /auth/change-password`: password debole → 422; password valida
   → 204; il refresh token emesso PRIMA del cambio password è stato
   rifiutato (401) da `POST /auth/refresh` DOPO il cambio.
6. `POST /auth/logout` con un refresh token nel body → 204; quello
   stesso refresh token non funziona più su `POST /auth/refresh` (401).

Anche verificato: il bundle frontend servito da Docker (nginx) contiene
davvero le nuove route (`grep 2fa-setup` sui bundle JS), e le pagine
`/` e `/login` rispondono 200 attraverso nginx. **Non verificato
manualmente in un browser reale** (solo via curl/script), stessa
limitazione già presente nella sessione 1.

## Stato attuale dell'ambiente Docker

Lo stack è stato lasciato **in esecuzione** al termine della sessione
(non fermato). Nel DB di sviluppo esistono ora, come residuo dei test:
- Un utente Admin: `admin@lavoro.internal` (2FA attiva).
- Un utente Operator: `operator@lavoro.internal` (2FA disattivata di
  nuovo a seguito del test di reset/recovery, password cambiata durante
  i test in `NewStr0ngPw!456`).
- Un lockout Redis su `bruteforce-target@lavoro.internal` (email
  inesistente, TTL ~15 minuti, si esaurisce da solo).

Se si riparte in un ambiente Docker diverso/pulito, questi dati non ci
saranno: rieseguire `alembic upgrade head` + `create_admin.py` come da
`README.md`.

## PROGETTO.md aggiornato

- Sezione "1. Autenticazione / 2FA": tutte e 6 le checkbox spuntate
  `[x]`, con una nota implementativa per ciascuna.
- `docs/SICUREZZA.md`: sezioni 1 ("Autenticazione JWT") e 2 ("2FA TOTP")
  riscritte per riflettere l'implementazione reale (nomi endpoint
  corretti, meccanismo di revoca `jti`/`sst`, rate limiting, policy
  Operator, rotazione backup codes, recovery admin-driven). Tabella RBAC
  (sezione 3) aggiornata per la policy 2FA di Operator.

## Prossimi passi consigliati

1. Se si vuole proseguire con `PROGETTO.md`, la prossima sezione logica
   è "2. Database / migrazioni" (indici, retention, backup, partitioning,
   seed dati di sviluppo — solo le migrazioni iniziali erano già fatte)
   oppure "9. Observability" (nessuna dashboard Grafana, nessun endpoint
   `/metrics`, nessun log verso Loki: tutto ancora da fare).
2. Non è mai stata fatta una **navigazione manuale in un browser reale**
   del flusso 2FA (login → setup obbligatorio → dashboard): consigliato
   prima di considerare la sezione 1 definitivamente chiusa lato UX, non
   solo lato contratto API.
3. Valutare se estendere il rate limiting anche per IP (oggi è solo per
   email/utente) se il rischio di brute-force distribuito è rilevante.
4. `backend/uv.lock` non è ancora stato generato (stessa nota aperta
   della sessione 1).

## File chiave da leggere per ripartire (sessione 2)

- `PROGETTO.md` sezione 1 — cosa è stato deciso e implementato.
- `backend/app/security/deps.py` — enforcement 2FA obbligatoria e revoca
  token, il cuore di questa sessione.
- `backend/app/api/v1/auth.py` — tutti gli endpoint di autenticazione.
- `backend/app/security/redis_client.py` — blacklist e rate limiting.
- `frontend/src/context/AuthContext.tsx` e
  `frontend/src/routes/TwoFactorSetupPage.tsx` — lato frontend del
  flusso di enrollment obbligatorio.
- `docs/SICUREZZA.md` — documentazione aggiornata del modello di
  sicurezza.

---

# Sessione 3 — 29 agosto 2026

## Richiesta

Completare `PROGETTO.md` § 2 "Database / migrazioni" (5 dei 6 punti erano
ancora da fare), poi § 3 "Frontend" (12 punti). Sessione partita in **plan
mode** per entrambe le parti; piano approvato salvato (fuori dal repo) in
`C:\Users\pierl\.claude\plans\in-questa-cartella-crea-cuddly-jellyfish.md`
(sovrascritto a ogni nuova richiesta di piano in questa sessione).

## Parte A — § 2 Database / migrazioni (completata)

Decisioni prese con l'utente: retention con default ragionevoli proposti
(non una decisione legale bloccante), backup locali riutilizzabili in
Docker Compose (non off-site, dipende dall'hosting definitivo non ancora
scelto), partitioning solo valutato per iscritto (volume reale oggi zero).

**Backend**:
- 2 nuove migrazioni Alembic: `20260829090000_export_jobs_expires_at.py`
  (colonna `export_jobs.expires_at`) e
  `20260829091500_additional_indexes.py` (composito
  `advertisements(source_id, status)`, GIN full-text su
  `advertisements`, `media(perceptual_hash)`, composito
  `export_jobs(status, requested_at)`, `export_jobs(requested_by_user_id)`,
  `scrape_errors(created_at)`, `audit_log(created_at)`). Modelli
  SQLAlchemy aggiornati in parallelo (`__table_args__`/`index=True`) per
  non creare drift con un futuro `alembic --autogenerate`.
- Nuovi settings in `backend/app/config.py`: `AUDIT_LOG_RETENTION_DAYS`
  (365), `SCRAPE_ERROR_RETENTION_DAYS` (90), `EXPORT_RETENTION_DAYS` (7),
  `BACKUP_RETENTION_DAYS` (14, letto dagli script di backup, non da
  Pydantic Settings).
- Nuovo `backend/app/workers/tasks_maintenance.py`
  (`cleanup_expired_data`): cancella `audit_log`/`scrape_errors` scaduti,
  per gli `export_jobs` scaduti rimuove l'oggetto MinIO e azzera
  `object_key` MANTENENDO la riga (storico export preservato). Schedulato
  alle 3:00 UTC via `celery_app.conf.beat_schedule`, eseguito sulla coda
  `maintenance` aggiunta al worker `worker-scraper` esistente (nessun
  nuovo servizio Celery).
- Nuovo `backend/app/scripts/seed_sources.py`: crea le 9 fonti da
  `app/scrapers/registry.SCRAPER_REGISTRY` (slug/base_url riusati dalle
  classi scraper stesse), idempotente.
- Due nuovi servizi `docker-compose.yml`: `backup-postgres` (dump
  giornaliero compresso + rotazione, `infra/backup/backup-postgres.sh`,
  usa `pg_dump --clean --if-exists` così il dump è ri-applicabile su un
  DB già popolato) e `backup-minio` (replica continua `mc mirror
  --overwrite --remove`, `infra/backup/backup-minio.sh` — non uno
  snapshot datato, quindi `BACKUP_RETENTION_DAYS` non si applica lì).
  Script di ripristino manuale `infra/backup/restore-postgres.sh`
  (mai automatico, operazione distruttiva).
- `docs/DATABASE.md` riscritto per intero: la versione precedente
  descriveva uno schema "aspirazionale" mai esistito nel codice reale
  (campi come `advertisement.city`, `external_id`, `sources.
  rate_limit_config` non esistono) — ora riflette lo schema vero.

**Verifica dal vivo** (Docker Desktop, stack già disponibile da sessioni
precedenti): 4 migrazioni applicate in sequenza su Postgres reale da un
volume pulito; `seed_sources.py` eseguito due volte (9 create, poi 0
create/9 già presenti); `cleanup_expired_data` eseguito manualmente contro
righe con `created_at`/`expires_at` forzati nel passato via SQL diretto —
cancellazione selettiva confermata (solo le righe scadute sparite),
oggetto MinIO di un export scaduto "tentato" (bucket assente, gestito
senza crash, solo warning); backup Postgres forzato (`--once`) e
**ripristinato con successo sullo stesso database popolato** (dati e
indici intatti dopo `restore-postgres.sh`); backup MinIO forzato
(comportamento corretto in assenza del bucket, mai creato perché
l'upload media reale è un TODO separato, § "Storage/media").

**Bug trovato e corretto durante la verifica** (non della sezione 2 in
sé, scoperto perché per la prima volta la lista fonti non era vuota):
`GET /sources` rispondeva con `itemsLast24H` (H maiuscola) invece di
`itemsLast24h`, per un difetto di `pydantic.alias_generators.to_camel`
sui confini cifra/lettera (`to_camel("items_last_24h") ==
"itemsLast24H"`). Corretto con un alias esplicito
(`Field(alias="itemsLast24h")`) in `backend/app/schemas/sources.py`. Non
era mai emerso prima perché nei test precedenti la tabella `sources` era
sempre stata vuota.

Dati di test sintetici creati per la verifica sono stati ripuliti a fine
sessione; restano nel DB solo dati "utili": 9 fonti seedate, l'utente
Admin con 2FA attiva (residuo delle sessioni precedenti).

`PROGETTO.md` § 2: tutte e 5 le checkbox rimanenti spuntate `[x]`, con
nota implementativa e di verifica per ciascuna (stesso stile della § 1).

## Parte B — § 3 Frontend (completata)

Decisioni prese con l'utente: aggiungere i piccoli endpoint backend
mancanti invece di limitare la UI ai dati già disponibili (storico
versioni AI Summary, storico run per fonte); collegare in UI sia
creazione utente sia reset 2FA (endpoint backend già esistenti,
inutilizzati); dark mode con palette completa + toggle persistente, non
un'approssimazione; test E2E con Playwright, eseguiti realmente contro lo
stack Docker, non solo scritti.

### Backend: 2 endpoint minimi aggiunti

- `GET /records/{id}/ai-summary/versions` — storico completo delle
  versioni (`backend/app/api/v1/records.py`, `app/schemas/records.py:
  RecordAiSummaryVersionRead`), prima il backend esponeva solo l'ultima.
- `GET /sources/{id}/runs` — storico run + errori annidati per fonte
  (`backend/app/api/v1/sources.py`, `app/schemas/sources.py:
  ScrapeRunRead`/`ScrapeErrorRead`), prima assente del tutto.
- Nuovi test in `backend/tests/test_camel_schemas.py` (inclusa una
  regressione esplicita per il bug `itemsLast24h` trovato nella parte A,
  non coperto da alcun test esistente).
- **Due bug trovati e corretti mentre si collegavano gli endpoint Admin in
  UI**: `POST /admin/users` rispondeva con uno schema (`UserRead`,
  snake_case) diverso da tutti gli altri endpoint dell'area
  (`AdminUserRead`, camelCase) — corretto in `backend/app/api/v1/
  admin.py` (ora ritorna `AdminUserRead`, la classe `UserRead` ormai
  inutilizzata è stata rimossa da `app/schemas/admin.py`).

### Frontend: fondamenta condivise (create prima di tutto il resto)

- `src/lib/errors.ts` (nuovo): `describeError(error)` — mappa un
  `ApiError` (403/404/429 con `retry_after_seconds`/5xx) o un errore di
  rete su `{title, description, retryable, retryAfterSeconds?}`.
- `src/components/ui/ErrorState.tsx` (nuovo) ed `ErrorRow` esteso in
  `src/components/ui/Table.tsx` (ora accetta `error={...}` con Retry
  automatico, oltre al vecchio `message="..."` retrocompatibile).
- `src/components/ErrorBoundary.tsx` (nuovo): React Error Boundary attorno
  a tutta l'app (`main.tsx`), fallback "Reload page" invece di una
  schermata bianca su crash di rendering.
- Dark mode: **tutti** i colori Tailwind (`tailwind.config.ts`) convertiti
  da hex statici a `rgb(var(--color-x) / <alpha-value>)`; le variabili
  vere e proprie (valori light + blocco `.dark` completo) vivono in
  `src/index.css`. I ruoli Material-3 "fixed"/"fixed-dim" restano identici
  in entrambi i temi per design (nessuna voce nel blocco `.dark`). Script
  inline in `index.html` applica il tema PRIMA del primo paint (niente
  flash). `src/context/ThemeContext.tsx` (nuovo, `light`/`dark`/`system`,
  persistito in `localStorage`), toggle nel Topbar. Sostituiti anche tutti
  i `bg-white` letterali (28 occorrenze, 12 file) con `bg-surface-
  container-lowest` (stesso colore in light, adattivo in dark) — nel farlo
  corretti 2 punti dove `bg-white` e `hover:bg-surface-container-lowest`
  coincidevano, rendendo l'hover invisibile.
- `src/components/ui/Dialog.tsx`: aggiunto focus trap (Tab/Shift+Tab
  vincolati dentro il modale), chiusura con Escape, ripristino del focus
  precedente alla chiusura, `aria-labelledby`.
- Nuovi tipi (`src/types/index.ts`), funzioni API (`src/api/records.ts`,
  `sources.ts`, `admin.ts`) e hook TanStack Query (`src/hooks/
  useRecords.ts`, `useSources.ts`, `useAdmin.ts`) per i 2 endpoint backend
  sopra e per createUser/resetTwoFactor.

### Frontend: pagine (3 agenti in parallelo, poi verifica/fix manuali)

- **Login + 2FA**: countdown lockout (`src/hooks/useCountdown.ts`,
  deduplicato da un identico copia-incolla dei due agenti in
  `LoginPage.tsx`/`TwoFactorSetupPage.tsx`), messaggi distinti per
  errore/lockout.
- **Ricerca**: filtri sincronizzati con l'URL (`useSearchParams`),
  dropdown "Source Origin" popolato da `GET /sources` (prima 3 valori
  hardcoded mai esistiti), errori uniformati.
- **Dettaglio Record**: selettore storico versioni AI Summary, eventi
  "Cambio annuncio canonico" evidenziati nello storico.
- **Gestione Fonti**: righe espandibili con drill-down run/errori,
  azioni nascoste per il ruolo Viewer.
- **Export**: polling automatico (ogni 3s se un job è `processing`).
- **Admin**: form "Create user" + bottone "Reset 2FA" per riga, filtri
  client-side sull'Audit Log.

### Bug trovati durante la verifica manuale (dopo il lavoro dei 3 agenti)

1. I due agenti "Login/Search" e "Admin/AI-Summary" hanno duplicato
   identico l'hook `useCountdown` in due file — estratto in
   `src/hooks/useCountdown.ts` condiviso.
2. `getByLabel("Source Origin")` falliva nei test E2E: i `<label>` dei
   filtri di ricerca non avevano `htmlFor`/`id` (vero difetto di
   accessibilità, non solo un problema di test) — corretto in
   `SearchPage.tsx`, aggiunto anche `aria-label` sui due input data.
3. I testi dei nuovi dialog "Create user"/"Reset 2FA" in `AdminPage.tsx`
   erano stati scritti in **italiano** dall'agente che li ha implementati,
   incoerenti con il resto dell'interfaccia (inglese) — tradotti per
   intero (label, bottoni, messaggi di errore/conferma).
4. Il locator del test E2E per la card export "Text Only" era ambiguo
   (`locator("div", {has: heading})` risolveva a 3 elementi) — aggiunto
   `data-testid="export-card-{type}"` alle card in `ExportsPage.tsx`.

### Verifica end-to-end reale

`npx tsc -b --noEmit` e `npm run lint` puliti (0 errori). `npm run build`
pulito. Rebuild + riavvio reale di `api`/`frontend` su Docker. Suite
Playwright (`frontend/e2e/`, `playwright.config.ts`) eseguita **davvero**
con `npx playwright test` contro lo stack Docker live: 8/9 passati, 1
skippato correttamente (nessun export "ready" esiste in questo ambiente,
il worker reale non è implementato). Verificati dal vivo anche via
`curl`: `POST /admin/users` (shape `AdminUserRead` confermata) e `POST /
admin/users/{id}/reset-2fa`; dati di test ripuliti a fine sessione. Dark
mode e focus trap del `Dialog` verificati con uno script Playwright
temporaneo (non committato, cancellato a fine verifica): toggle applica
`html.dark`, persiste al reload, sfondo cambia davvero colore (RGB
confermato); il `Dialog` sposta il focus al suo interno all'apertura e si
chiude con Escape.

## File chiave da leggere per ripartire (sessione 3)

- `docs/DATABASE.md` — schema reale, retention, backup, partitioning.
- `backend/app/workers/tasks_maintenance.py` — task di retention.
- `infra/backup/` — script di backup/ripristino.
- `backend/app/schemas/sources.py` — dove si trova il fix `itemsLast24h`
  (attenzione a questa classe di bug se si aggiungono altri campi con
  cifre in `CamelModel`: verificare sempre `to_camel(nome_campo)` a mano).
- `frontend/src/lib/errors.ts`, `src/components/ui/ErrorState.tsx` —
  gestione errori uniforme, usata ovunque nel frontend.
- `frontend/src/context/ThemeContext.tsx`, `src/index.css` — come
  funziona il dark mode (variabili CSS, non varianti `dark:` sparse).
- `frontend/e2e/` — suite Playwright, `fixtures.ts` contiene le
  credenziali dell'Admin di test e il secret TOTP usati dai test (validi
  solo finché quell'utente esiste in quell'ambiente Docker).

---

# Sessione 4 — 29 agosto 2026

## Richiesta

Completare `PROGETTO.md` § 4 "Scraper per fonte". La formulazione
originale della sezione chiedeva selettori di scraping reali per 9 fonti
specifiche (siti commerciali di annunci di servizi sessuali). L'utente ha
anche chiesto in aggiunta la possibilità di aggiungere nuove fonti da
scrapare direttamente dentro l'applicazione.

## Decisione di sicurezza e redirezione dell'utente

Ho rifiutato di scrivere selettori CSS hardcoded per le 9 fonti nominate:
raccogliere sistematicamente numeri di telefono e media da quei siti
avrebbe significato costruire uno strumento pronto per stalking/doxxing/
molestie contro una popolazione vulnerabile, senza modo di verificare
un'autorizzazione legale — posizione mantenuta indipendentemente dal
contesto d'uso dichiarato. Il piano iniziale proposto in plan mode (solo
infrastruttura CRUD generica, nessuno scraper reale) è stato **respinto
esplicitamente dall'utente**: *"crea uno scarper reale e poi sono io che
metto i siti da cui deve fare scraping. Cambia il piano per fare questo"*.

Ho rivisto il piano di conseguenza: costruire un **motore di scraping
generico ma REALE** (fetch e parsing HTML via Scrapling — non stub),
dove è l'operatore (l'utente), tramite
l'app, a fornire URL e selettori CSS per ciascuna fonte — il motore stesso
non conosce alcun sito specifico. Ho mantenuto di mia iniziativa (non
richiesto esplicitamente, ma non contestato) due vincoli di sicurezza
incorporati nel motore e non disattivabili da configurazione: rispetto
automatico di `robots.txt` prima di ogni richiesta e un rate limit minimo
(1s tra le richieste). Lo User-Agent è ora configurabile per singola fonte
tramite `scrapeConfig.userAgent`, con fallback al default del progetto.
Il piano rivisto è stato approvato dall'utente.

## Cosa è stato costruito

### Backend

- Nuova colonna `sources.scrape_config` (JSONB, nullable) + migrazione
  Alembic `20260830090000_sources_scrape_config.py`.
- `app/services/robots_check.py` (nuovo): fetch e parsing di `robots.txt`
  reale (`urllib.robotparser`), usato sia dall'enforcement automatico sia
  dal tool di verifica manuale.
- `app/scrapers/generic.py` (nuovo): `GenericScraper(Scraper)`, motore
  reale config-driven — `discover()` segue paginazione fino a
  `max_pages`/`max_ads_per_run`, `scrape_ad()` applica i selettori CSS
  configurati, `download_media()` scarica le immagini, `normalize()`
  mappa sul formato comune. Ogni richiesta passa da `_get()`, che verifica
  `robots.txt` PRIMA di procedere (altrimenti `RobotsDisallowedError`) e
  applica il rate limit.
- `app/services/media_storage.py` (nuovo): sniffing MIME via magic bytes
  (senza `imghdr`, rimosso in Python 3.13) + upload reale su MinIO.
- `app/services/scrape_ingest.py` (nuovo): orchestrazione reale
  `collect_ads()` (fase async, solo rete) + `persist_collected_ads()`
  (fase sync, solo DB) — riusa i servizi già esistenti e già testati
  `phone_crypto.py`/`dedup.py`/`canonical.py` invece di reimplementarli.
  **Prima pipeline di ingestione scraping→persistenza end-to-end del
  progetto** (finora era solo modellata, mai eseguita).
- `app/workers/tasks_scraper.py`: `run_scrape_source` ora esegue
  davvero la pipeline sopra se `source.scrape_config` è valorizzato,
  altrimenti mantiene il comportamento stub precedente.
- `app/schemas/sources.py`: nuovi `ScrapeConfigInput`/`ScrapeFieldConfig`/
  `SourceCreate`/`SourceUpdate`/`SourceDetailRead`/`RobotsCheckRead`/
  `TestConfigResult`, con validazione URL e campo `phone` obbligatorio.
- `app/api/v1/sources.py`: CRUD completo (`POST/GET/PATCH/DELETE
  /sources/{id}`, solo Admin per scrittura, 409 su delete con annunci
  collegati), più `POST /sources/{id}/check-robots` e `POST /sources/{id}
  /test-config` (dry-run, non scrive su DB).
- 9 test nuovi in `backend/tests/scrapers/` (server HTTP locale reale con
  fixture HTML sintetiche, nessuna rete reale — incluso un test che
  verifica che un `robots.txt` con `Disallow: /` blocchi davvero il
  motore) + 8 test schema in `test_sources_schemas.py`. Suite completa
  85/85.

### Frontend

- `SourcesPage.tsx` riscritta: form "Add/Edit Source" con sezione di
  configurazione scraping completa (start URLs, selettori, campi
  dinamici), bottoni "Check robots.txt"/"Test configuration"/"Delete",
  badge "Connector broken?" quando `consecutiveFailures >= 3`.
- Nuovi tipi/funzioni API/hook per tutti gli endpoint sopra
  (`types/index.ts`, `api/sources.ts`, `hooks/useSources.ts`).

### Bug pre-esistente trovato e corretto

`GET /sources` non esponeva mai il campo `priority` reale: la colonna
"Priority" in UI mostrava un'etichetta High/Medium/Low fabbricata a
partire da `errorRate` (un tasso di errore travestito da priorità).
Corretto aggiungendo `priority` a `SourceRead` e usando il valore vero in
UI.

## Verifica dal vivo (Docker reale)

Creata via API una fonte di test puntata a un server HTTP locale
sintetico (le stesse fixture usate dai test pytest, esposte al container
via `host.docker.internal`), verificati `check-robots` e `test-config`,
eseguito uno scan reale che ha scaricato le pagine con rate limiting
osservabile (~1s tra le richieste), creato 2 `Record`/`Advertisement`
reali (il terzo annuncio di fixture, senza telefono, correttamente
scartato) e caricato 2 media reali su MinIO (verificato via
`list_objects`), con `canonical_ad_id` impostato correttamente. Verificato
anche il blocco 409 su `DELETE` con annunci collegati. Tutti i dati/media
di test rimossi a fine sessione, server di test locale fermato.

## PROGETTO.md aggiornato

Sezione 4: le 9 checkbox per-fonte restano `[ ]` (nessun selettore
scritto per quei siti specifici — vedi motivazione sopra), nota
introduttiva riscritta per spiegare il motore generico. Aggiunte/spuntate
`[x]`: motore di scraping generico reale, CRUD fonti completo, policy
User-Agent/rate-limit, enforcement+verifica `robots.txt`, dashboard/alert
fonti rotte (`consecutiveFailures`).

## Prossimi passi consigliati

1. Prossima sezione logica di `PROGETTO.md`: "5. AI / classificazione
   media" (oggi solo placeholder a regole, mai sostituito da un modello
   reale).
2. Se si vuole attivare per davvero una delle 9 fonti storiche: prima
   verificare ToS/robots.txt di quel sito specifico (decisione umana,
   fuori dallo scope di questa sessione), poi configurarne i selettori
   dall'app (vedi `docs/SVILUPPO.md` § 7).
3. Non ancora affrontato: gestione blocchi IP/captcha/proxy rotation
   (decisione con impatto su costi, esplicitamente lasciata aperta).

## File chiave da leggere per ripartire (sessione 4)

- `backend/app/scrapers/generic.py` — il motore di scraping generico.
- `backend/app/services/scrape_ingest.py` — la pipeline di ingestione
  reale (collect + persist).
- `backend/app/services/robots_check.py` — enforcement `robots.txt`.
- `backend/app/api/v1/sources.py` e `app/schemas/sources.py` — CRUD fonti
  e validazione configurazione.
- `frontend/src/routes/SourcesPage.tsx` — form di configurazione fonte.
- `docs/SVILUPPO.md` § 7 — come configurare una fonte generica senza
  scrivere codice.

---

# Sessione 5 — 1 settembre 2026

## Richiesta e decisioni approvate

L'utente ha chiesto di implementare integralmente il piano relativo ai
punti 5 e 6 di `PROGETTO.md`: sostituzione dei placeholder AI/media,
pipeline asincrone, revisione umana, limiti operativi, storage sicuro,
FFmpeg, watermark autorizzato, lifecycle MinIO e aggiornamento frontend.

Decisioni applicate:

- OpenAI Responses API con Structured Outputs, `store=false`, modello
  predefinito configurabile `gpt-5.6-luna` e prompt `summary-v1`.
- AI disabilitata finché chiave e tutti i budget configurabili non hanno
  valori positivi; nessun fallback al vecchio generatore template.
- Nessun telefono, URL personale o media inviato a OpenAI. Telefoni e URL
  vengono redatti anche quando compaiono nel testo libero degli annunci;
  le fonti sono inviate come riferimenti interni e rimappate localmente.
- NudeNet 3.4.2/ONNX 320n come classificatore locale. Nessuna stima
  automatica dell'età: nudità esplicita insieme a un volto produce solo
  `possibleMinorReview=true` e revisione obbligatoria.
- Soglie: `explicit >= 0.65`, `safe < 0.20`, fascia intermedia o errore
  `unclassified` con trattamento sensibile.
- Watermark removal disabilitata per default e attivabile solo da Admin,
  per singola fonte, con riferimento autorizzativo e regioni valide.
- Limiti: immagini 15 MB/40 MP; video 100 MB/300 secondi. Nessuna CDN per
  ora; rivalutazione oltre 100 GB/mese di egress o p95 media > 500 ms per
  due settimane.

## Backend e database implementati

### Modelli e migrazione

- Nuova migrazione
  `backend/migrations/versions/20260901090000_ai_media_pipeline.py`, head
  unica dopo `20260830090000`. Gli enum PostgreSQL usano
  `create_type=False` per evitare il precedente `DuplicateObjectError`.
- Nuova tabella `summary_generation_jobs` con stato
  `pending/processing/completed/failed`, utente richiedente, modello,
  prompt, input hash, versione risultante, cache hit, errore sicuro e
  timestamp.
- `summary_versions` ora salva provider, modello, prompt version, input
  hash, token input/output/cache, job e cache metadata. Vincolo univoco su
  record/hash/modello/prompt per evitare versioni duplicate concorrenti.
- `media` ora distingue chiavi original/display/thumbnail e salva
  dimensione, risoluzione, durata, stato/errori di processing, segnali
  safety e stato/note/autore/timestamp della revisione.
- `sources` contiene configurazione watermark: enabled, riferimento
  autorizzativo e regioni normalizzate.
- `backend/uv.lock` è stato generato con le nuove dipendenze.

### Classificazione e processing media

- `app/services/media_classifier.py`: classificatore reale
  `NudeNetOnnxMediaClassifier`, modello lazy e versionato
  `nudenet-3.4.2-320n`; segnali `explicitContent`, `explicitScore`,
  `faceVisible`, `faceScore`, `watermarkPresent` e
  `possibleMinorReview`. Il vecchio nome `RuleBasedMediaClassifier` resta
  solo come alias retrocompatibile verso l'implementazione reale.
- `app/services/media_processing.py`: validazione Pillow/ffprobe,
  inpainting OpenCV, transcodifica FFmpeg H.264/AAC CRF 23, yuv420p,
  faststart e massimo 1280x720; thumbnail JPEG max 640 e cinque frame al
  10/30/50/70/90%. Comandi con `shell=False`, timeout e directory
  temporanee isolate.
- `app/workers/tasks_media.py`: task idempotente/ritentabile che scarica
  l'originale da MinIO, genera varianti, classifica e aggiorna
  atomicamente media/history/audit. Gli originali non vengono mai
  sovrascritti.
- `GenericScraper` ora scarica media con streaming limitato, redirect
  manuali rivalidati, blocco SSRF per schemi non HTTP(S) e indirizzi
  privati/reserved, Content-Length, risposta troncata e limite dinamico
  immagine/video. Magic bytes e decoder reali decidono l'accettazione.
- `tasks_scraper.py` accoda il processing media soltanto dopo il commit.

### Riepiloghi OpenAI

- `app/services/summary_generator.py`: rimosso il generatore template;
  adapter OpenAI Responses con output Pydantic strutturato, `store=false`,
  timeout, prompt cache key e usage token. Nessun modello alternativo.
- `app/workers/tasks_ai.py`: job persistente asincrono, input minimizzato,
  hash deterministico, cache hit senza nuova chiamata/versione, retry con
  backoff soltanto per timeout/connessione/429/5xx e stato failed sicuro
  per errori permanenti.
- Redis applica limite richieste giornaliero per utente, richieste/minuto
  provider e budget token globale. La stima viene prenotata prima della
  chiamata, riconciliata con l'uso effettivo e rilasciata se la chiamata
  fallisce.
- `POST /records/{id}/ai-summary/regenerate` risponde 202 con il job;
  `GET /records/{id}/ai-summary/jobs/{jobId}` espone lo stato. Lettura
  ultima versione e storico restano compatibili.

### API, RBAC, storage e manutenzione

- `POST /media/{id}/review`: Admin/Operator può applicare override
  esplicito con note, autore, history e audit.
- `POST /media/{id}/reprocess`: riaccoda media falliti/pregressi.
- Contratti `MediaRead`/`RecordMedia` estesi con classificazione,
  confidenza, segnali, review/processing state e URL original/display/
  thumbnail.
- Gli URL `/media-objects/...` sono stati sostituiti da presigned URL
  MinIO brevi, costruiti con `MINIO_PUBLIC_ENDPOINT`.
- Task Beat giornaliero configura lifecycle per oggetti `tmp/` e multipart
  incompleti dopo un giorno; task notturno elimina solo oggetti media più
  vecchi della grace period e non referenziati da nessuna colonna DB.

## Frontend implementato

- La tab AI Summary avvia il job asincrono, effettua polling ogni due
  secondi e mostra processing/errore/completamento, invalidando riepilogo
  e storico al termine.
- La tab Media mostra processing, classificazione e badge "Needs review";
  Admin/Operator possono marcare safe/explicit con note e riaccodare media
  falliti. Media non classificati o in review restano trattati come
  sensibili.
- Il form Sources espone configurazione watermark Admin-only con
  autorizzazione e regione normalizzata; backend e frontend condividono
  lo stesso contratto camelCase.

## Test e verifiche eseguite

- `ruff check .`: pulito.
- Suite backend completa: **115 passed, 5 skipped**. Gli skip sono test
  opt-in già previsti; 19 warning provengono da lxml/curl_cffi su Windows.
- Test nuovi coprono soglie e aggregazione NudeNet, versione modello,
  immagine innocua con inferenza reale, watermark/originale immutabile,
  MIME e file corrotti, FFmpeg reale su MP4 sintetico, cinque frame,
  risoluzione/thumbnail, Structured Output simulato, token usage,
  minimizzazione URL/telefono, hash deterministico, AI disabilitata e
  schema del dataset redatto.
- `npm run lint`: 0 errori, due warning Fast Refresh preesistenti in
  `AuthContext.tsx` e `ThemeContext.tsx`.
- `npm run build`: completata; Vite segnala soltanto un warning relativo a
  un `tsconfig.base.json` esterno non presente, senza bloccare TypeScript o
  bundle.
- Alembic: `20260901090000 (head)`; import completo FastAPI riuscito.
- Build Docker backend reale completata nell'immagine locale
  `lavoro-esterno-backend:points-5-6` con FFmpeg 7.1.5, OpenCV,
  ONNX Runtime, NudeNet e OpenAI SDK.
- Smoke test nell'immagine: FastAPI caricato e task Celery media/AI
  registrati; `ffmpeg -version` riuscito.
- Il PostgreSQL temporaneo avviato per una migrazione live è stato
  arrestato e rimosso. L'esecuzione di `alembic upgrade head` contro quel
  container non è avvenuta perché l'autorizzazione specifica è stata
  rifiutata dall'utente/ambiente.
- Nessuna chiamata OpenAI live: mancano intenzionalmente API key e budget
  espliciti. Il comportamento fail-closed è stato verificato con test.
- Playwright end-to-end dei nuovi flussi non è stato eseguito perché lo
  stack completo con DB/account 2FA non è stato avviato in questa sessione.

## Documentazione aggiornata

- `PROGETTO.md`: punti 5 e 6 descritti nel dettaglio e spuntati, con note
  trasparenti sui limiti della verifica live.
- `README.md`, `docs/API.md`, `docs/ARCHITETTURA.md`,
  `docs/DATABASE.md`, `docs/SICUREZZA.md`, `docs/SVILUPPO.md` aggiornati.
- `docs/SICUREZZA.md` documenta minimizzazione, `store=false`, retention
  standard dei log OpenAI fino a 30 giorni e il fatto che ZDR richiede
  idoneità/approvazione separata.

## Stato e prossimi passi consigliati

Il codice dei punti 5 e 6 è implementato. Prima di un deploy effettuare:

1. Avviare uno stack Docker con `.env` di sviluppo valido e applicare
   `docker compose exec api alembic upgrade head`, verificando tabelle,
   enum e worker reali su PostgreSQL/Redis/MinIO.
2. Eseguire Playwright sui nuovi flussi AI/media con un account Admin 2FA
   e fixture sintetiche.
3. Eseguire il test OpenAI live solo con chiave dedicata e budget
   positivi minimi; verificare job, usage, cache hit e output redatto.
4. Verificare lifecycle MinIO e orphan cleanup su oggetti sintetici,
   confermando che gli originali referenziati non vengano eliminati.
5. La generazione export reale, la retention e i flussi GDPR sono stati
   completati nella sessione 6 riportata più avanti in questo documento.

## File chiave da leggere per ripartire (sessione 5)

- `backend/migrations/versions/20260901090000_ai_media_pipeline.py`
- `backend/app/services/media_classifier.py`
- `backend/app/services/media_processing.py`
- `backend/app/services/summary_generator.py`
- `backend/app/workers/tasks_media.py`
- `backend/app/workers/tasks_ai.py`
- `backend/app/workers/tasks_maintenance.py`
- `backend/app/api/v1/media.py`, `records.py`, `sources.py`
- `frontend/src/routes/records/RecordAiSummaryTab.tsx`
- `frontend/src/routes/records/RecordMediaTab.tsx`
- `frontend/src/routes/SourcesPage.tsx`
- `backend/tests/test_media_classifier.py`
- `backend/tests/test_media_processing.py`
- `backend/tests/test_summary_ai.py`
- `PROGETTO.md` § 5-6 e documentazione in `docs/`.

---

# Sessione 6 — 2 settembre 2026: Export e Sicurezza/GDPR

## Risultato

Completata la sezione 7 e i punti 2–5 della sezione 8 di `PROGETTO.md`:

- export ZIP asincroni su coda/worker `exports`, scope obbligatorio,
  manifest versionato, JSON/CSV e sole varianti media visualizzabili;
- relazione `export_job_records`, limiti 1.000 record/2 GiB, storage MinIO,
  presigned download auditato, ownership Operator e cleanup DB/object;
- retention configurabile per annunci/media/log/audit, con ricalcolo del
  canonico e invalidazione delle copie export;
- workflow Admin di cancellazione con anteprima/conferma, job persistente e
  registro HMAC di soppressione controllato dall'ingestione;
- telefono completo sempre per Admin e tramite grant individuale per gli
  altri ruoli, masking predefinito, `Cache-Control: no-store` e audit;
- security workflow con Bandit, pip-audit, npm audit, dependency review,
  Trivy e ZAP; report interno in `docs/SECURITY_REVIEW_2026-09-02.md`.

## Migrazione e file chiave

- Head Alembic: `20260902090000_exports_privacy.py`.
- Nuovi modelli: `privacy.py`; estesi `users.py` ed `export_jobs.py`.
- Nuovi worker: `tasks_exports.py`, `tasks_privacy.py`; retention riscritta
  in `tasks_maintenance.py`.
- Nuova API: `/privacy/erasure-requests`; export e admin estesi.
- UI: scope/monitoraggio Export, selezione dalla ricerca, grant telefono e
  tab Admin Privacy/Erasure.

## Verifiche eseguite

- `ruff check`: superato.
- `pytest`: 121 passed, 5 skipped opzionali.
- frontend lint: nessun errore (2 warning Fast Refresh preesistenti).
- frontend build Vite 8.2.2: superata.
- Bandit: nessun Medium/High.
- pip-audit e npm audit: zero vulnerabilità note dopo remediation.
- migrazione applicata realmente su PostgreSQL 17 temporaneo fino a head.
- build Docker backend/frontend completate; entrambe le immagini usano utenti
  non privilegiati (`app` e UID 101).
- Trivy config scan finale senza High/Critical dopo la remediation dei
  container root.
- `docker compose config --quiet` superato con `.env.example`; la copia `.env`
  temporanea usata per il controllo è stata rimossa.

## Gate ancora esterni

- Gli scan completi Trivy immagini e ZAP sono configurati in CI; i report del
  runner devono essere archiviati prima del go-live.
- Playwright richiede lo stack persistente e l'account Admin 2FA delle fixture:
  non è stato rieseguito localmente in questa sessione.
- Restano obbligatori pentest indipendente autenticato, TLS/HSTS/CSP con i
  domini definitivi, secret manager e prova di restore staging.
- I punti 1 (validazione legale fonti) e 6 (DPA/conformità provider LLM)
  della sezione 8 restano deliberatamente aperti.

---

# Sessione 7 — Stato definitivo e avvio locale su Windows

## Stato consolidato

- La sezione 7 di `PROGETTO.md` è completata: gli export sono job asincroni,
  usano una relazione DB per congelare lo scope e vengono elaborati dal worker
  Celery dedicato `worker-exports` sulla coda `exports`.
- Gli ZIP sono salvati sotto `exports/` in MinIO, hanno manifest versionato,
  JSON/CSV, hash SHA-256 e includono solo varianti display/thumbnail; gli
  originali immutabili non vengono esportati.
- I punti 2–5 della sezione 8 sono completati per la parte interna: retention
  configurabile, cancellazione GDPR asincrona con registro HMAC di
  soppressione, permesso individuale per il telefono in chiaro e security
  review automatizzata/manuale.
- Il gate di produzione resta separato: pentest esterno, TLS/secret manager,
  restore verificato e report completi Trivy/ZAP devono essere chiusi prima
  del go-live.
- L'head Alembic corrente è `20260902090000` (`exports_privacy`) e deve essere
  applicato prima di usare le nuove API.

## Avvio rapido con Docker Compose (PowerShell)

Prerequisiti: Docker Desktop avviato con Docker Compose v2. Eseguire i comandi
dalla directory radice `lavoro-esterno-1`.

### 1. Preparare l'ambiente

```powershell
Copy-Item .env.example .env
```

Generare segreti distinti. Eseguire due volte il comando da 32 byte per
`PHONE_ENCRYPTION_KEY` e `PHONE_HMAC_SECRET`, senza riutilizzare lo stesso
valore:

```powershell
[Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)
```

Generare separatamente il segreto JWT da 64 byte:

```powershell
[Convert]::ToBase64String(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(64)
)
```

Aprire `.env` e sostituire almeno tutti i valori `change-me-*`. In particolare:

- assegnare i tre valori appena generati a `PHONE_ENCRYPTION_KEY`,
  `PHONE_HMAC_SECRET` e `JWT_SECRET_KEY`;
- dopo aver modificato `POSTGRES_PASSWORD`, riportare la stessa password in
  `DATABASE_URL` e `DATABASE_URL_SYNC`;
- mantenere `MINIO_ACCESS_KEY` coerente con `MINIO_ROOT_USER` e
  `MINIO_SECRET_KEY` coerente con `MINIO_ROOT_PASSWORD`;
- impostare una password dedicata in `GF_SECURITY_ADMIN_PASSWORD`.

Non committare `.env`. Il riepilogo OpenAI rimane intenzionalmente disabilitato
se `OPENAI_API_KEY` è vuota oppure se uno tra
`AI_USER_DAILY_REQUEST_LIMIT`, `AI_GLOBAL_DAILY_TOKEN_BUDGET` e
`AI_PROVIDER_REQUESTS_PER_MINUTE` è assente o uguale a zero. Per abilitarlo
servono una chiave valida e valori positivi per tutti e tre i limiti.

### 2. Costruire e avviare lo stack

```powershell
docker compose up -d --build
docker compose ps
```

Attendere che PostgreSQL, Redis e MinIO risultino healthy. L'API e i worker
dipendono da questi servizi e possono richiedere qualche secondo aggiuntivo al
primo avvio.

### 3. Applicare le migrazioni

Le migrazioni non vengono applicate automaticamente all'avvio dell'API:

```powershell
docker compose exec api alembic upgrade head
docker compose exec api alembic current
```

Il secondo comando deve riportare `20260902090000 (head)`.

### 4. Creare il primo Admin

La creazione iniziale avviene fuori dall'API perché la gestione utenti richiede
già un Admin autenticato con 2FA:

```powershell
docker compose exec api python -m app.scripts.create_admin `
  --email admin@lavoro.internal `
  --password "UnaPasswordForte123!"
```

Sostituire la password di esempio con una password univoca. Aprire poi
`http://localhost`, accedere con l'account appena creato e completare il setup
2FA guidato dalla UI. Salvare immediatamente i backup code: vengono mostrati
una sola volta.

### 5. Indirizzi locali

- Applicazione: `http://localhost`
- Swagger/OpenAPI: `http://localhost/docs`
- Console MinIO: `http://localhost:9001`
- Grafana: `http://localhost:3000`
- Prometheus: `http://localhost:9090`

### 6. Diagnostica

```powershell
docker compose ps
docker compose logs -f api
docker compose logs -f worker-exports
docker compose logs -f worker-media
docker compose logs -f worker-ai
```

Ogni comando `logs -f` rimane in ascolto; interromperlo con `Ctrl+C` prima di
passare al successivo. Per esaminare anche scraping, retention e scheduler usare
rispettivamente `worker-scraper` e `scheduler`.

### 7. Arresto sicuro

```powershell
docker compose down
```

Questo arresta i container conservando i volumi PostgreSQL, MinIO e gli altri
dati locali. La variante `docker compose down -v` elimina i volumi e quindi i
dati: è un'operazione distruttiva, da usare solo quando la cancellazione
completa dell'ambiente è esplicitamente voluta e dopo aver verificato eventuali
backup.

## Troubleshooting Docker Desktop/Windows

### `localhost` restituisce HTTP 500 o resta in attesa

Su Docker Desktop con backend WSL, `localhost` può risolvere prima a `::1` e
venire intercettato da `wslrelay` senza raggiungere nginx. Le porte nginx sono
perciò pubblicate esplicitamente su `127.0.0.1`; il browser deve quindi poter
ripiegare immediatamente su IPv4. Per distinguere un problema del relay da un
errore applicativo usare:

```powershell
curl.exe --noproxy "*" -4 -I http://localhost/
curl.exe --noproxy "*" -4 http://localhost/api/v1/healthz
```

Entrambe le richieste devono raggiungere nginx; la prima restituisce `200`.
Come alternativa diagnostica temporanea aprire direttamente
`http://127.0.0.1`. Dopo una modifica alle porte ricreare soltanto nginx:

```powershell
docker compose up -d --force-recreate nginx
```

Se `::1:80` continua a risultare in ascolto dopo la ricreazione, verificare il
processo con `Get-NetTCPConnection -State Listen -LocalPort 80`: può trattarsi
di un `wslrelay` rimasto in memoria con il vecchio mapping. In questa sessione
anche il riavvio di Docker Desktop non lo ha rimosso; il relay è stato
terminato solo dopo averne controllato PID e tutte le porte inoltrate. Questa
operazione può interrompere temporaneamente altri servizi WSL e non va eseguita
alla cieca. Dopo la rimozione del relay stale, `localhost` è tornato a
ripiegare su `127.0.0.1` e ha risposto HTTP 200.

### I container backup falliscono su `set -eu`

Gli script montati nei container Alpine devono avere terminatori LF. Il file
`.gitattributes` impone `eol=lf` a tutti i file `.sh`. Il sintomo tipico di un
checkout CRLF è `set: illegal option -` oppure `set: -\r: invalid option`.
Dopo un riavvio del motore Docker, se PostgreSQL o MinIO non sono ancora
raggiungibili, i backup ritentano dopo 60 secondi; un dump PostgreSQL viene
pubblicato soltanto quando `pg_dump` e la compressione sono entrambi riusciti.
Dopo aver normalizzato un checkout, ricreare solo i servizi backup:

```powershell
docker compose up -d --force-recreate backup-postgres backup-minio
docker compose ps backup-postgres backup-minio
docker compose logs --tail=50 backup-postgres backup-minio
```

Questi comandi non eliminano né ricreano i volumi dati.

### Verifica della correzione del 2 settembre 2026

- `backup-minio.sh`, `backup-postgres.sh` e `restore-postgres.sh`: zero byte
  CR/CRLF;
- backup PostgreSQL: dump valido completato e rotazione eseguita;
- backup MinIO: bucket applicativo creato vuoto e mirror completato;
- `backup-postgres`, `backup-minio` e `nginx`: stato `Up` stabile;
- `http://localhost/` e `GET /api/v1/healthz`: HTTP 200;
- nessun volume Docker è stato eliminato o ricreato.
