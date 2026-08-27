# PROGETTO.md - Checklist per portare "Lavoro Esterno" in produzione

Questo documento elenca in modo concreto tutto ciò che resta da fare per
passare dall'infrastruttura/base creata (docker-compose, documentazione,
CI, scheletro repo) a un sistema pronto per la produzione. Aggiornare le
checkbox man mano che gli elementi vengono completati.

## 1. Autenticazione / 2FA

- [ ] Decidere e implementare la policy MFA per il ruolo **Operator**
      (oggi solo "raccomandata"): obbligatoria da subito, obbligatoria
      dopo N giorni di grazia, o solo Admin — decisione di prodotto.
- [ ] Implementare la procedura di **recovery account** quando un utente
      perde sia il dispositivo TOTP sia i backup codes (oggi previsto
      solo "reset da Admin" a livello di design, manca l'endpoint/flow
      completo e la relativa voce di audit log).
- [ ] Definire e implementare la **rotazione/scadenza dei backup codes**
      (quanti codici generare, se rigenerarli automaticamente dopo
      l'uso dell'ultimo).
- [ ] Implementare **rate limiting sui tentativi di login e di verifica
      TOTP** (protezione da brute force), con blocco temporaneo account.
- [ ] Definire policy di **complessità/scadenza password** (se richiesta
      da requisiti di conformità del cliente).
- [ ] Implementare **revoca/blacklist dei refresh token** su logout e su
      cambio password/reset 2FA (richiede storage lato server, es. Redis
      o tabella dedicata).

## 2. Database / migrazioni

- [ ] Scrivere le migrazioni Alembic iniziali per tutte le tabelle
      descritte in `docs/DATABASE.md` (record, advertisement, media,
      sources, canonical_history, scrape_runs, scrape_errors,
      media_classification_history, summary_versions, export_jobs,
      audit_log, users).
- [ ] Definire e creare gli **indici** definitivi oltre a quelli minimi
      già identificati (es. indici compositi per i filtri di ricerca più
      usati: città + data, fonte + stato, full-text su descrizione).
- [ ] Definire la **retention policy per categoria di dato** (annunci,
      media, log, export scaduti, audit log) e implementarla come task
      periodico dello scheduler — dipendenza: decisione legale/prodotto,
      vedi sezione 8.
- [ ] Configurare **backup automatici** di PostgreSQL (dump periodici +
      test di ripristino) e di MinIO (versioning o replica) — dipendenza:
      scelta dell'ambiente di hosting definitivo.
- [ ] Valutare **partitioning** delle tabelle ad alto volume
      (`advertisement`, `scrape_errors`) se il volume di dati atteso è
      elevato nel tempo.
- [ ] Popolare un **seed di sviluppo** (fixture) per le 9 fonti previste,
      utile per testare frontend/API senza scraping reale.

## 3. Frontend

- [ ] Rifinire la pagina/tab di **Login + 2FA** (stato di errore chiaro
      su codice TOTP errato, countdown per nuovo tentativo dopo blocco).
- [ ] Rifinire la pagina/tab di **Ricerca** (filtri combinabili, stato
      vuoto, stato di errore rete, paginazione/infinite scroll).
- [ ] Rifinire la pagina/tab di **Dettaglio Record** (annuncio canonico,
      storico canonical_history, galleria media con stato classificazione,
      riepilogo AI con storico versioni e azione "rigenera").
- [ ] Rifinire la pagina/tab di **Gestione Fonti** (solo Admin/Operator a
      seconda dei permessi: stato attivo/disattivo, storico run, avvio
      manuale run, visualizzazione errori scraping).
- [ ] Rifinire la pagina/tab di **Export** (creazione job, stato in
      tempo reale/polling, storico job utente, download).
- [ ] Rifinire la pagina/tab di **Amministrazione utenti** (solo Admin:
      creazione utente, cambio ruolo, reset 2FA, disattivazione).
- [ ] Rifinire la pagina/tab di **Audit log** (solo Admin: filtri per
      utente/azione/data).
- [ ] Gestione uniforme degli **stati di errore** (rete, 401/403, 404,
      500) con componenti condivisi, non gestione ad-hoc per pagina.
- [ ] Passata di **accessibilità** (contrasto colori, navigazione da
      tastiera, attributi ARIA su componenti custom, focus management nei
      modali).
- [ ] Implementare **dark mode** (già previsto da Tailwind: definire i
      token colore e il toggle persistente per utente).
- [ ] Test end-to-end almeno sui flussi critici (login+2FA, ricerca,
      export) — scegliere strumento (es. Playwright).

## 4. Scraper per fonte

Per ciascuna fonte elencata, il lavoro da fare è lo stesso schema:
verificare `robots.txt`/ToS, implementare i selettori reali (oggi non
esistono connettori funzionanti, solo l'interfaccia `base.py` prevista),
scrivere test con fixture HTML salvate, validare rate limiting.

- [ ] **escort_advisor**: validare ToS/robots.txt, implementare
      selettori reali, gestire eventuale paginazione/login richiesto, test.
- [ ] **bakeca_incontri**: validare ToS/robots.txt, implementare
      selettori reali, test.
- [ ] **moscarossa**: validare ToS/robots.txt, implementare selettori
      reali, test.
- [ ] **megaescort**: validare ToS/robots.txt, implementare selettori
      reali, test.
- [ ] **escortforumit**: validare ToS/robots.txt (nota: è un forum,
      struttura dati diversa dagli annunci classici, potrebbe richiedere
      parsing dedicato dei thread), implementare selettori reali, test.
- [ ] **escortacom**: validare ToS/robots.txt, implementare selettori
      reali, test.
- [ ] **rosa_rossa**: validare ToS/robots.txt, implementare selettori
      reali, test.
- [ ] **torino_erotica**: validare ToS/robots.txt, implementare
      selettori reali, test.
- [ ] **punterforum**: validare ToS/robots.txt (anche questo un forum,
      stessa nota di escortforumit), implementare selettori reali, test.
- [ ] Definire una **policy comune di User-Agent/identificazione** dello
      scraper e un piano di gestione per eventuali blocchi IP/captcha
      (proxy rotation? — decisione da prendere, ha impatto su costi).
- [ ] Dashboard/alert per **fonti che smettono di funzionare**
      (cambio struttura HTML del sito sorgente).

## 5. AI / classificazione media

- [ ] Sostituire il **placeholder di classificazione media** con un
      classificatore ONNX reale (oggi non esiste un modello integrato):
      scegliere/addestrare il modello, definire la tassonomia di
      classificazione (es. volto visibile, watermark, presenza minori —
      requisito di sicurezza critico, non solo qualità dati).
- [ ] Sostituire il **placeholder di generazione riepilogo** con un
      generatore reale basato su LLM: scegliere il provider (OpenAI,
      Anthropic, self-hosted) — dipendenza: decisione su costi e policy
      sui dati inviati a provider terzi (dati personali, vedi sezione 8).
- [ ] Definire e implementare **gestione costi/rate limit** verso il
      provider LLM/inference (batching, cache dei riepiloghi già
      generati, limiti per utente/periodo).
- [ ] Definire **versioning di modello e prompt** (già previsto nello
      schema `summary_versions.model_provider/model_name/prompt_
      version`) e processo di valutazione qualità quando si cambia
      modello o prompt.
- [ ] Definire soglie di **confidenza minima** sotto le quali la
      classificazione media va marcata come "da revisione umana"
      piuttosto che applicata automaticamente.

## 6. Storage / media

- [ ] Implementare la **rimozione filigrane (watermark)** nei casi
      autorizzati — dipendenza: chiarire esattamente in quali casi è
      legalmente/contrattualmente autorizzato farlo, non è solo una
      questione tecnica.
- [ ] Implementare la **pipeline FFmpeg per preview video** (estrazione
      frame di anteprima, eventuale transcodifica per compatibilità
      browser, generazione thumbnail).
- [ ] Definire policy di **dimensione massima/validazione file** in
      upload/download media (oggi solo `client_max_body_size` lato nginx
      come limite generico).
- [ ] Configurare **lifecycle policy MinIO** (es. classi di storage,
      pulizia automatica media orfani non più collegati a nessun
      annuncio attivo).
- [ ] Valutare **CDN/cache** per la distribuzione dei media se il volume
      di traffico lo giustifica.

## 7. Export

- [ ] Implementare la **generazione reale del pacchetto zip con
      manifest** (oggi solo lo schema `export_jobs` è definito, manca la
      logica di generazione: raccolta record filtrati, inclusione media,
      creazione manifest con provenienza dati).
- [ ] Decidere su quale **coda Celery** eseguire il task di export (oggi
      non assegnata esplicitamente: valutare se serve una coda dedicata
      `exports` oltre a `scraping`/`media`/`ai`, per non competere con
      il carico di classificazione media).
- [ ] Implementare lo **storage temporaneo** dei pacchetti generati su
      MinIO con URL firmati a scadenza.
- [ ] Implementare il **job periodico di pulizia** dei job di export
      scaduti (`export_jobs.expires_at`), sia il record DB sia il file
      su MinIO.
- [ ] Definire limiti su **dimensione massima/numero di record per
      export** per evitare export che saturano risorse o tempo.

## 8. Sicurezza / GDPR

- [ ] Ottenere **validazione legale specialistica** sullo scraping di
      dati personali (numeri di telefono, contenuti media) da fonti
      terze, con particolare attenzione alle 9 fonti elencate in
      sezione 4 (richiamo a `docs/SICUREZZA.md` §7 e al §21 del PDF di
      progetto).
- [ ] Definire e rendere **configurabile la retention** per ogni
      categoria di dato (annunci, media, log, audit log) — collegata al
      punto 2 (retention policy DB).
- [ ] Definire e implementare le **procedure di cancellazione dati** su
      richiesta (diritto all'oblio), incluso l'impatto sulla
      deduplicazione (cosa succede a un `record` se uno degli annunci
      collegati va cancellato).
- [ ] Definire policy di **accesso e minimizzazione visualizzazione** del
      numero di telefono in chiaro (chi può vederlo per esteso vs. solo
      mascherato, quali azioni vengono loggate in `audit_log` quando il
      dato in chiaro viene effettivamente decifrato e mostrato).
- [ ] Eseguire un **penetration test / security review** prima del go-live
      (vedi anche skill `security-review` disponibile nel repo per una
      prima passata automatizzata, non sostitutiva di un audit esterno).
- [ ] Verificare conformità nell'invio di dati a provider LLM esterni
      (sezione 5) rispetto ai requisiti GDPR (minimizzazione, eventuale
      DPA con il provider).

## 9. Observability

- [ ] Costruire le **dashboard Grafana specifiche** del progetto (oggi
      solo il provisioning datasource è predisposto, nessuna dashboard
      esiste ancora): almeno (a) salute API (latenze, error rate,
      richieste/minuto), (b) stato worker Celery per coda (lunghezza
      coda, task falliti, tempo di esecuzione), (c) stato scraping per
      fonte (successo/fallimento run, nuovi annunci trovati).
- [ ] Implementare l'**endpoint `/metrics`** lato API (oggi solo
      referenziato in `infra/prometheus/prometheus.yml`, da implementare
      nel backend, es. via `prometheus-fastapi-instrumentator`).
- [ ] Configurare l'**invio dei log applicativi a Loki** (oggi Loki gira
      ma nulla scrive log verso di lui: serve un driver/agent, es.
      Promtail o driver di logging Docker, oppure logging diretto via
      client HTTP Loki dal backend).
- [ ] Definire **alerting** (Grafana Alerting o Alertmanager) su almeno:
      API down, coda Celery bloccata/troppo lunga, run di scraping
      falliti ripetutamente per una fonte, spazio disco MinIO/Postgres.
- [ ] Valutare l'aggiunta di **postgres_exporter** (già predisposto come
      job commentato in `infra/prometheus/prometheus.yml`) e di un
      eventuale exporter per Redis/Celery.

## 10. Deploy

- [ ] Definire e provisionare l'**ambiente di staging** e quello di
      **produzione** (hosting: VPS dedicato, cloud provider — decisione
      da prendere con il cliente).
- [ ] Configurare **dominio e DNS** per l'ambiente pubblico.
- [ ] Configurare **TLS** (es. Let's Encrypt/reverse proxy con
      certificati automatici, o terminazione TLS a livello di load
      balancer/CDN a monte di `nginx`) — nel setup attuale nginx espone
      solo la porta 80 in chiaro.
- [ ] Configurare **backup automatici** end-to-end (Postgres + MinIO) con
      test periodico di ripristino (collegato al punto 2).
- [ ] Implementare **secrets management** in produzione (oggi solo file
      `.env` locale): valutare un vault/secrets manager del provider
      cloud scelto, evitare segreti in chiaro sulle macchine di deploy.
- [ ] Restringere l'esposizione pubblica di **MinIO console (9001)**,
      **Grafana (3000)** e **Prometheus (9090)**: nel `docker-compose.yml`
      attuale sono pubblicate per comodità di sviluppo, in produzione
      vanno messe dietro VPN/autenticazione o rimosse da `ports:`.
      pubblico.
- [ ] Configurare **pipeline di deploy** (CD) — oggi la CI
      (`.github/workflows/ci.yml`) fa solo lint/test/build immagini,
      senza push né deploy: aggiungere step di push su registry e deploy
      automatico/manuale verso staging/produzione.
- [ ] Definire strategia di **scaling dei worker Celery** per coda in
      base al carico reale (numero di repliche per `worker-scraper` /
      `worker-media` / `worker-ai`).
- [ ] Definire piano di **disaster recovery** (RPO/RTO) concordato con il
      cliente.

## 11. Note di compromesso su questa consegna

`frontend/` e `backend/` sono stati completati e la coerenza con
`docker-compose.yml`/`.env.example` è stata verificata a posteriori:
- `command` dei servizi Celery corretto a `-A app.workers.celery_app`
  (il modulo reale, non `app.worker`).
- `.env.example` allineato ai nomi effettivi letti da `backend/app/config.py`
  (`DATABASE_URL` in schema `asyncpg`, aggiunta `DATABASE_URL_SYNC` per i
  worker, `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`/`MINIO_SECURE`,
  `JWT_ACCESS_TTL_MINUTES`/`JWT_REFRESH_TTL_DAYS`, singola `JWT_SECRET_KEY`).
- `docker-compose.yml` passa `VITE_API_URL` come build arg al servizio
  `frontend` (necessario perché Vite lo "bake-a" nel bundle statico a
  build-time, non a runtime), puntato al reverse proxy pubblico e non alla
  porta interna 8000 dell'api.
- Aggiunto `.gitignore` root mancante.
- `.github/workflows/ci.yml` corretto: nessun `uv.lock` è ancora committato
  (rimosso `--frozen`), env var di test allineate, rimosso lo step di build
  Docker per `nginx` (nel compose usa l'immagine ufficiale con config
  montata, non un Dockerfile dedicato).
- Contratto API backend↔frontend riconciliato con un passaggio dedicato
  (endpoint `dashboard`, `records/*`, `sources/*`, `exports/*`, `admin/*`
  mancanti sono stati implementati nel backend per soddisfare esattamente
  le chiamate in `frontend/src/api/*.ts`) e poi verificato ulteriormente a
  mano: sono stati trovati e corretti altri due mismatch sfuggiti al primo
  giro, entrambi bloccanti per l'uso base dell'app:
  - `POST /auth/login`/`login-2fa`/`GET /auth/me` rispondevano con
    `requires_2fa`/`login_ticket` e senza l'oggetto `user`, mentre il
    frontend (`frontend/src/api/auth.ts`) si aspetta `status`/`mfa_token`
    e un `user` con `id/email/name/role/mfaEnabled/status` — schema e
    router riscritti (`backend/app/schemas/auth.py:UserPublic`,
    `backend/app/api/v1/auth.py`). `user.name`/`user.status` sono derivati
    (email/`is_active`), nessuna colonna dedicata nel modello `User`.
  - `GET /sources` rispondeva con la forma "grezza" del modello (`slug`,
    `base_url`, `priority`, snake_case) invece di `code`/`country`/
    `lastRunAt`/`itemsLast24h`/`errorRate` in camelCase attesi dal
    frontend — corretto in `backend/app/schemas/sources.py` (ora
    `CamelModel`) e `backend/app/api/v1/sources.py` (calcolo aggregato da
    `scrape_runs`, N+1 accettato per il volume di fonti atteso). `country`
    resta un placeholder fisso `"N/D"`.
  Entrambe le correzioni sono state verificate con `python -m py_compile`,
  import completo di `app.main` (41 route registrate) e l'intera suite
  pytest (54/54 passati).

## 12. Verifica end-to-end reale (`docker compose up --build`) e bug trovati

A differenza delle verifiche precedenti (solo statiche: compilazione, test
unitari), in questa sessione lo stack è stato **davvero avviato** con
Docker Desktop e testato dal vivo. Sono emersi e sono stati corretti
diversi bug che nessuna verifica statica poteva intercettare:

- **`npm install` falliva** (`ERESOLVE`): `eslint-plugin-react-hooks@^4.6.2`
  non supporta ESLint 9. Aggiornato a `^5.0.0` in `frontend/package.json`.
- **`npm run build` falliva** (errori TypeScript): mancava
  `frontend/src/vite-env.d.ts` (necessario per i tipi di `import.meta.env`),
  `tsconfig.node.json` non aveva `"types": ["node"]`/`@types/node` come
  dipendenza (necessario per `node:url` in `vite.config.ts`), e un import
  `Badge` inutilizzato in `RecordOccurrencesTab.tsx`. Tutti corretti;
  `npm run build` e `npm run lint` sono ora puliti (0 errori).
- **`eslint.config.js` segnalava decine di falsi `no-undef`** su tipi DOM
  ambientali TypeScript (`HTMLDivElement`, `RequestInit`, ecc., che non
  sono globals runtime): `no-undef` disabilitato per i file TS/TSX (tsc
  già copre questo caso con piena informazione di tipo).
- **`pip install -e .` falliva nel Dockerfile del backend**: `pyproject.toml`
  dichiarava `readme = "README.md"` ma quel file non esiste in
  `backend/`. Rimosso il campo (non obbligatorio).
- **Le migrazioni Alembic fallivano** con `DuplicateObjectError: type
  "user_role" already exists` al primo `alembic upgrade head` su un DB
  vuoto: gli enum Postgres venivano creati esplicitamente
  (`enum_type.create(bind, checkfirst=True)`) E ricreati implicitamente
  da `op.create_table` (l'oggetto `postgresql.ENUM` senza
  `create_type=False` spara un secondo `CREATE TYPE` come effetto
  collaterale della creazione della tabella). Corretto aggiungendo
  `create_type=False` a tutti gli 8 enum in
  `backend/migrations/versions/20260827120000_initial_schema.py`.
  Verificato: `docker compose exec api alembic upgrade head` crea ora
  tutte le 12 tabelle correttamente su un Postgres reale.
- **Nessun modo di creare il primo utente Admin**: `POST /admin/users`
  richiede già un Admin autenticato con 2FA attiva (corretto come modello
  di sicurezza, ma è un problema di bootstrap). Aggiunto
  `backend/app/scripts/create_admin.py`, script one-shot da eseguire con
  `docker compose exec api python -m app.scripts.create_admin --email
  ... --password ...`, documentato in `README.md` e `docs/SVILUPPO.md`.
- **`GET /api/v1/sources` e `GET /api/v1/exports` rispondevano 307**
  (redirect a `.../sources/`, `.../exports/`) quando chiamati senza
  slash finale, come fa il frontend: FastAPI genera un redirect quando la
  route è registrata come `@router.get("/")` sotto un prefisso. Corretto
  cambiando la route in `@router.get("")` in `sources.py`, `exports.py`
  (get e post) e, per coerenza, `search.py`.
- `docs/SVILUPPO.md` conteneva istruzioni non allineate al codice reale
  (nomi metodi scraper inventati, campi `sources` inesistenti come
  `rate_limit_config`/`robots_txt_checked_at`, endpoint `POST
  /sources/{id}/runs` mai esistito, variabili JWT vecchie): corretto per
  riflettere l'interfaccia `Scraper` reale (`discover`/`scrape_ad`/
  `download_media`/`normalize`) e gli endpoint effettivamente presenti.
- **`loki` in crash-loop**: `infra/loki/loki-config.yml` aveva
  `compactor.retention_enabled: true` senza `delete_request_store`,
  richiesto dalle versioni recenti di Loki quando la retention è attiva.
  Aggiunto `delete_request_store: filesystem` (coerente con lo storage
  filesystem locale già configurato). Verificato: il container resta
  stabile ("Loki started") invece di riavviarsi in loop.

**Verificato con successo dal vivo** (Docker Desktop, `docker compose up
--build` con tutti i 13 servizi): build di tutte le 6 immagini custom,
avvio di tutti i container, `alembic upgrade head` con creazione delle 12
tabelle, bootstrap del primo Admin, `POST /api/v1/auth/login` con risposta
esatta attesa dal frontend (`status`/`access_token`/`refresh_token`/
`user`), `GET /auth/me`, `GET /sources`, `GET /sources/summary`, `GET
/exports`, `GET /dashboard/kpis`, `GET /admin/users` tutti raggiungibili
tramite il reverse proxy nginx su `http://localhost/` con risposta 200 e
forma corretta. Il bundle frontend è stato verificato contenere l'URL API
corretto (`http://localhost/api/v1`, iniettato da `VITE_API_URL` come
build-arg).

**Non ancora verificato**: navigazione manuale dell'interfaccia in un
browser reale (solo l'API è stata esercitata via `curl`), flusso 2FA
completo (setup QR code + verifica + login con TOTP), scraper reali,
generazione export reale, dashboard Grafana.

Resta da fare un giro di verifica **eseguendo davvero** `docker compose up
--build` end-to-end (non ancora testato in questo ambiente per assenza di
Docker), e generare un `uv.lock`/`package-lock.json` reali eseguendo
`uv sync` e `npm install` in locale.
