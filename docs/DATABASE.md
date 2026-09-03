# Database - Lavoro Esterno

Database PostgreSQL 17, schema gestito con SQLAlchemy 2 (modelli in
`backend/app/models/`) e Alembic (migrazioni in `backend/migrations/
versions/`). A differenza di una versione precedente di questo documento,
qui sotto sono elencate le colonne **realmente esistenti nel codice**, non
uno schema aspirazionale: se una colonna non è elencata, non esiste ancora.

## 1. Perché il telefono non è una chiave primaria in chiaro

Il numero di telefono è il criterio principale di deduplicazione tra
annunci, ma è anche un dato personale sensibile. Per questo:

- Il valore in chiaro **non viene mai usato come chiave di ricerca/join**
  né salvato senza cifratura.
- Viene cifrato con **AES-256-GCM** (chiave `PHONE_ENCRYPTION_KEY`, 32
  byte, da `.env`) prima di essere scritto su disco (`records.
  phone_encrypted`): solo l'applicazione, in possesso della chiave, può
  decifrarlo per la visualizzazione autorizzata.
- Per permettere comunque ricerca esatta e deduplicazione senza decifrare
  ogni riga, viene calcolato in parallelo un **hash HMAC-SHA256** del
  numero normalizzato E.164 (`records.phone_lookup_hash`, `PHONE_HMAC_
  SECRET`): deterministico (stesso numero → stesso hash) ma non
  invertibile, indicizzato univocamente per i lookup di deduplicazione e
  ricerca per telefono.
- Effetto pratico: un accesso non autorizzato al solo database (senza le
  chiavi applicative) non espone i numeri di telefono in chiaro, mentre
  l'applicazione può comunque deduplicare in modo efficiente tramite
  l'indice sull'hash.

Vedi `backend/app/services/phone_crypto.py` per l'implementazione.

## 2. Tabelle (schema reale)

### `users`
- `id` UUID PK
- `email` String(320), **unique, index**
- `password_hash` String(255)
- `role` enum `user_role` (`admin` / `operator` / `viewer`), default `viewer`
- `totp_secret_encrypted` bytes nullable (cifrato AES-256-GCM, stessa
  primitiva del telefono), `totp_enabled` bool default `false`
- `backup_codes_hash` JSONB nullable (lista hash argon2 dei backup code
  monouso)
- `is_active` bool default `true`
- `security_stamp_at` timestamptz, `server_default=now()` — invalida in
  blocco tutti i JWT emessi prima di questo istante (claim `sst`), usato
  da logout/cambio password/reset 2FA (vedi `docs/SICUREZZA.md`)
- `created_at`, `updated_at` (mixin comune)

### `records`
Entità "numero di telefono univoco", aggrega N `advertisements`.
- `id` UUID PK
- `phone_encrypted` bytes (AES-256-GCM)
- `phone_lookup_hash` String(64), **unique, index**
- `canonical_ad_id` UUID nullable, FK → `advertisements.id` (`use_alter`
  per spezzare il ciclo di dipendenza DDL con `advertisements`, che a sua
  volta referenzia `records.id`)
- `created_at`, `updated_at`

### `advertisements`
Singolo annuncio scrapato da una fonte.
- `id` UUID PK
- `record_id` UUID, FK → `records.id` ondelete CASCADE, **index**
- `source_id` UUID, FK → `sources.id` ondelete RESTRICT, **index**
- `source_url` Text
- `title` Text nullable, `description` Text nullable
- `content_hash` String(64) nullable, **index** (SHA-256 del contenuto
  normalizzato, per rilevare ripubblicazioni identiche)
- `first_seen_at`, `last_seen_at` (aggiornato via `onupdate`), `scraped_at`
- `confidence` Float default `1.0`
- `status` enum `advertisement_status` (`active` / `removed` / `invalid`)
- **Nessun campo città/età/external_id**: non esistono nel modello attuale.
  Se in futuro serve idempotenza per-fonte (evitare di ricreare lo stesso
  annuncio a ogni scan), andrà aggiunto un campo `external_id` + un
  vincolo `unique(source_id, external_id)` — non presente oggi.

### `media`
File (immagine/video) associato a un annuncio.
- `id` UUID PK
- `advertisement_id` UUID, FK → `advertisements.id` ondelete CASCADE, **index**
- `original_object_key` Text (chiave oggetto MinIO del file originale)
- `derived_object_key` Text nullable (compatibilità legacy),
  `display_object_key` e `thumbnail_object_key` Text nullable; l'originale
  non viene mai sovrascritto
- `sha256` String(64), **index** (dedup esatto)
- `perceptual_hash` String(64) nullable, **index** (dedup pHash, TODO in
  `app/services/dedup.py`)
- `mime_type` String(100)
- `classification` enum `media_classification` (`explicit` / `safe` /
  `unclassified`), default `unclassified`
- `classification_confidence` Float nullable, `classifier_version` String nullable
- `safety_signals` JSONB; `processing_status` enum
  (`pending`/`processing`/`ready`/`failed`) e `processing_error`
- `review_status` enum (`not_required`/`required`/`reviewed`), note,
  reviewer e timestamp
- `file_size_bytes`, `width`, `height`, `duration_seconds`
- `created_at`

### `sources`
- `id` UUID PK
- `name` String(200)
- `slug` String(100), **unique, index** — identificatore tecnico della
  fonte, libero (nessun connettore Python per-sito da risolvere: l'unico
  motore di scraping è quello generico configurabile, vedi
  `app/scrapers/generic.py`)
- `base_url` Text
- `priority` enum `source_priority` (`high` / `medium` / `low`), default `medium`
- `status` enum `source_status` (`healthy` / `degraded` / `offline`), default `healthy`
- `enabled` bool default `true`
- `scrape_config` JSONB, nullable — configurazione del motore di scraping
  generico (`app/scrapers/generic.py`, vedi § "Motore di scraping
  generico" sotto), unico motore esistente. Nullable: una fonte senza
  `scrape_config` non può essere scansionata (il run fallisce
  esplicitamente finché non viene configurata).
- `watermark_removal_enabled`, `watermark_authorization_reference` e
  `watermark_regions` JSONB: configurazione Admin-only, valida solo con
  autorizzazione e regioni normalizzate.
- `created_at`, `updated_at`

### `scrape_runs`
- `id` UUID PK
- `source_id` UUID, FK → `sources.id` ondelete CASCADE, **index**
- `started_at`, `finished_at` nullable
- `status` enum `scrape_run_status` (`running` / `completed` / `failed`)
- `items_found`, `items_new`, `errors_count` Integer, default `0`

### `scrape_errors`
- `id` UUID PK
- `scrape_run_id` UUID, FK → `scrape_runs.id` ondelete CASCADE, **index**
- `url` Text, `error_message` Text
- `created_at`, **index** (query di retention, vedi § 4)

### `canonical_history`
- `id` UUID PK
- `record_id` UUID, FK → `records.id` ondelete CASCADE, **index**
- `previous_advertisement_id` UUID nullable, FK → `advertisements.id` ondelete SET NULL
- `new_advertisement_id` UUID, FK → `advertisements.id` ondelete CASCADE
- `reason` Text
- `overridden_by_user_id` UUID nullable, FK → `users.id` ondelete SET NULL
  (valorizzato solo per override manuali, non per applicazioni automatiche
  della regola in `app/services/canonical.py`)
- `created_at`

### `media_classification_history`
- `id` UUID PK
- `media_id` UUID, FK → `media.id` ondelete CASCADE, **index**
- `previous_classification` enum nullable, `new_classification` enum
- `confidence` Float nullable
- `manual_override` bool default `false`
- `changed_by_user_id` UUID nullable, FK → `users.id` ondelete SET NULL
- `created_at`

### `summary_versions`
- `id` UUID PK
- `record_id` UUID, FK → `records.id` ondelete CASCADE, **index**
- `version` Integer
- `summary_json` JSONB (`{summary, advertisement_information,
  forum_information, unverified_claims, sources}`, vedi
  `app/services/summary_generator.py`)
- `model_name` String(200)
- `model_provider`, `prompt_version`, `input_hash`; token input/output/cache,
  `cache_hit` e FK opzionale al job di generazione. L'indice univoco
  `(record_id, input_hash, model_provider, model_name, prompt_version)`
  implementa la cache senza collisioni tra provider.
- `created_at`

### `summary_generation_jobs`
- `id` UUID PK; FK a `records` e all'utente richiedente
- stato enum `pending`/`processing`/`completed`/`failed`
- provider, modello, revisione congelata della configurazione, prompt version,
  input hash, versione risultante, cache hit ed errore sicuro; timestamp di
  creazione/avvio/completamento
- indici su record, utente, stato e input hash

### `ai_settings`
- singleton con PK `id = 1`
- `active_provider`, `prompt_version`
- limiti runtime: richieste giornaliere per utente, richieste/minuto per
  provider e budget token cloud giornaliero
- `revision` per aggiornamenti ottimistici e timestamp

### `ai_provider_configs`
- `provider` univoco tra Ollama, OpenAI, Anthropic, Google, Groq, Mistral,
  OpenRouter e custom OpenAI-compatible
- modello, stato abilitato, endpoint opzionale e opzioni non sensibili JSONB
- credenziale opzionale in `api_key_encrypted`, cifrata AES-256-GCM con la
  chiave separata `AI_CREDENTIAL_ENCRYPTION_KEY`
- revisione, esito/istante dell'ultimo test e timestamp; l'API espone solo il
  booleano `credentialConfigured`, mai ciphertext o chiave

### `export_jobs`
- `id` UUID PK
- `record_id` UUID nullable, FK → `records.id` ondelete CASCADE, **index**
  (nullable: un export può essere bulk, con l'elenco record in
  `manifest_json["record_ids"]` invece che una singola FK)
- `type` enum `export_type` (`text_only` / `complete_media` / `safe_complete`)
- `status` enum `export_status` (`pending` / `processing` / `ready` / `failed`)
- `progress_percent` Integer default `0`
- `requested_by_user_id` UUID, FK → `users.id` ondelete RESTRICT, **index**
- `requested_at`, `completed_at` nullable
- `manifest_json` JSONB nullable, `object_key` Text nullable, `error_message` Text nullable
- `expires_at` timestamptz nullable — calcolata a `requested_at +
  EXPORT_RETENTION_DAYS` da `app/api/v1/exports.py`, usata dal task di
  retention (§ 4) per rimuovere l'oggetto MinIO scaduto **senza cancellare
  la riga** (storico esportazioni preservato per audit)
- **Composito** `(status, requested_at)`, **index**

### `audit_log`
- `id` UUID PK
- `user_id` UUID nullable, FK → `users.id` ondelete SET NULL, **index**
  (nullable per azioni di sistema, es. il task di retention stesso)
- `action` String(200), `entity_type` String(100), `entity_id` String(100) nullable
- `details_json` JSONB nullable
- `created_at`, **index** (query di retention, vedi § 4)

## 3. Relazioni principali (riassunto)

```
sources 1───N advertisements N───1 records 1───N media (via advertisement)
                    │                 │
                    │                 ├──N canonical_history (storico)
                    │                 └──N summary_versions (storico)
                    │
                    └──N scrape_runs ──N scrape_errors

users 1───N export_jobs
users 1───N audit_log
media 1───N media_classification_history
```

## 4. Indici

Oltre agli indici mono-colonna su ogni FK e sui campi elencati sopra come
**index** (creati nella migrazione iniziale
`20260827120000_initial_schema.py`), la migrazione
`20260829091500_additional_indexes.py` aggiunge:

- `advertisements(source_id, status)` — filtro "annunci attivi di una
  fonte", usato dalla selezione canonica e da eventuali viste aggregate.
- Indice funzionale **GIN full-text** su `advertisements` (`to_tsvector
  ('simple', title || description)`, `ix_advertisements_fulltext`) — non
  una colonna, un'espressione: query di ricerca testuale via `@@
  plainto_tsquery(...)`. Se il volume di ricerche crescesse, valutare una
  colonna `tsvector` generata/materializzata (più performante, più costosa
  da mantenere) invece dell'indice funzionale.
- `media(perceptual_hash)`, `export_jobs(status, requested_at)`,
  `export_jobs(requested_by_user_id)`, `scrape_errors(created_at)`,
  `audit_log(created_at)`.

Nessun indice composito su una colonna "città" o simile: `advertisements`
non ha un campo geografico strutturato oggi (vedi § 2).

## 5. Retention policy

Nessuna scadenza automatica per dato "vivo" (`records`/`advertisements`/
`media`): la loro retention definitiva resta sospesa a una validazione
legale/GDPR (vedi `docs/SICUREZZA.md`). Per i dati accessori (log, export
scaduti), un task periodico Celery Beat applica default configurabili via
env, non vincolanti:

| Dato | Variabile | Default | Azione |
|---|---|---|---|
| `audit_log` | `AUDIT_LOG_RETENTION_DAYS` | 365 giorni | Riga cancellata |
| `scrape_errors` | `SCRAPE_ERROR_RETENTION_DAYS` | 90 giorni | Riga cancellata |
| `export_jobs` (pacchetto) | `EXPORT_RETENTION_DAYS` | 7 giorni | Oggetto MinIO rimosso, `object_key` azzerato; riga mantenuta |

Implementato in `backend/app/workers/tasks_maintenance.py`
(`cleanup_expired_data`), schedulato ogni notte alle 3:00 UTC via
`celery_app.conf.beat_schedule` (`app/workers/celery_app.py`), eseguito dal
worker `worker-scraper` (coda aggiuntiva `maintenance`, vedi
`docker-compose.yml` — nessun servizio Celery dedicato, il volume di
lavoro non lo giustifica).

Test manuale: `docker compose exec worker-scraper celery -A
app.workers.celery_app call app.workers.tasks_maintenance.cleanup_expired_data`.

## 6. Backup

Due servizi Docker Compose, locali (stesso host della sorgente — **non**
un backup off-site/disaster-recovery):

- **`backup-postgres`** (`postgres:17-alpine`): `pg_dump` compresso una
  volta al giorno su un volume dedicato `postgres-backups`, con rotazione
  (`BACKUP_RETENTION_DAYS`, default 14 giorni). Script:
  `infra/backup/backup-postgres.sh`. Ripristino manuale (mai automatico,
  è un'operazione distruttiva): `infra/backup/restore-postgres.sh
  <dump.sql.gz>`, eseguito con `docker compose exec backup-postgres`.
- **`backup-minio`** (`minio/mc`): **replica continua** (`mc mirror
  --overwrite --remove`, non snapshot datati) del bucket media su un
  volume dedicato `minio-backups`. `BACKUP_RETENTION_DAYS` non si applica
  qui (nessuno snapshot da ruotare): la variabile resta letta per
  coerenza e per un'eventuale futura evoluzione verso snapshot periodici.
  Script: `infra/backup/backup-minio.sh`. Verificato dal vivo: finché il
  bucket `lavoro-esterno-media` non esiste (nessun media è mai stato
  caricato, l'upload reale su MinIO è un TODO aperto in § "Storage /
  media" di `PROGETTO.md`), lo script logga un avviso e ritenta al ciclo
  successivo invece di fallire il container — comportamento corretto,
  nessuna azione richiesta finché quel TODO non è chiuso.

Quando si sceglie l'hosting definitivo, adattare entrambi gli script per
spedire una copia anche a uno storage remoto S3-compatible (i comandi
`pg_dump`/`mc mirror` supportano target remoti nello stesso modo).

## 7. Partitioning — valutazione (nessuna implementazione)

`advertisements` e `scrape_errors` sono le tabelle a più alto volume
atteso nel tempo (una riga per annuncio scrapato/per errore di scraping).
Oggi il volume reale è **zero** (nessuno scraper attivo, vedi
`PROGETTO.md` § 4): implementare il partitioning nativo Postgres ora
sarebbe prematuro e aggiungerebbe complessità (query planner, vincoli
unique/FK cross-partizione, manutenzione delle partizioni) senza alcun
beneficio misurabile.

Raccomandazione: rivalutare quando una delle due tabelle supera
indicativamente **qualche milione di righe** o **decine di GB**, con
partizionamento a range su `scraped_at` (per `advertisements`) o
`created_at` (per `scrape_errors`), granularità mensile o trimestrale.
Nota di costo: convertire una tabella esistente non partizionata in una
partizionata richiede ricrearla e fare backfill dei dati (Postgres non
supporta un `ALTER TABLE ... PARTITION BY` in-place) — un motivo in più
per non partizionare "per sicurezza" oggi, ma per farlo consapevolmente
quando il volume lo giustifica davvero, pianificando una finestra di
manutenzione per la migrazione.

## 8. Seed di sviluppo

Nessuno script di seed per `sources`: si crea una fonte via API/UI (`POST
/sources`, form "Add Source" nella pagina Sources), con o senza
`scrape_config`. Vedi `app/scripts/create_admin.py` per il bootstrap del
primo utente Admin (unico script "una tantum" rimasto).

## 9. Export e cancellazione GDPR

- `export_job_records` materializza lo scope di ogni export e consente di
  invalidare pacchetti contenenti un record soggetto a retention/oblio.
- `export_jobs` conserva conteggi, stima non compressa, dimensione ZIP,
  policy telefono e timestamp di avvio/completamento/scadenza.
- `erasure_requests` è il workflow persistente bozza -> pending ->
  processing -> completed/failed. Non espone né registra il telefono.
- `suppression_entries` contiene soltanto l'HMAC keyed già usato dalla
  deduplicazione, con vincolo unique. Non scade automaticamente finché
  continua il trattamento e impedisce allo scraper di ricreare il record.
- `users.can_view_clear_phone` è false per default; per gli Admin il
  permesso effettivo deriva dal ruolo e non dal flag.

La retention predefinita è annunci 365 giorni, media 180, scrape run/error
e Loki 90, audit 365, pacchetti export 7. Il valore `0` disabilita la
cancellazione automatica della relativa categoria DB.
