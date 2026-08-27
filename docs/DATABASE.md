# Database - Lavoro Esterno

Database PostgreSQL 17, schema gestito con SQLAlchemy 2 (modelli) e
Alembic (migrazioni, in `backend/migrations/`). Questo documento descrive
lo schema logico delle tabelle principali: i nomi esatti delle colonne
possono variare leggermente rispetto all'implementazione finale nei
modelli SQLAlchemy, ma la struttura relazionale e le motivazioni di design
descritte qui sono vincolanti.

## 1. Perché il telefono non è una chiave primaria in chiaro

Il numero di telefono è il criterio principale di deduplicazione tra
annunci, ma è anche un dato personale sensibile. Per questo:

- Il valore in chiaro **non viene mai usato come chiave di ricerca/join**
  né salvato senza cifratura.
- Viene cifrato con **AES-256-GCM** (chiave `PHONE_ENCRYPTION_KEY`, 32
  byte, da `.env`) prima di essere scritto su disco: solo l'applicazione,
  in possesso della chiave, può decifrarlo per la visualizzazione
  autorizzata.
- Per permettere comunque ricerca esatta e deduplicazione senza decifrare
  ogni riga, viene calcolato in parallelo un **hash HMAC-SHA256** del
  numero normalizzato (E.164), usando `PHONE_HMAC_SECRET`: questo hash è
  deterministico (stesso numero -> stesso hash) ma non invertibile, e
  viene indicizzato per i lookup di deduplicazione e ricerca per telefono.
- Effetto pratico: un accesso non autorizzato al solo database (senza le
  chiavi applicative) non espone i numeri di telefono in chiaro, mentre
  l'applicazione può comunque deduplicare in modo efficiente tramite
  l'indice sull'hash.

## 2. Tabelle principali

### `users`
Utenti dell'applicazione (accesso riservato, nessuna registrazione
pubblica).
- `id`, `email` (univoco), `password_hash`, `role` (`admin` / `operator`
  / `viewer`), `is_active`
- `totp_secret` (cifrato), `totp_enabled`, `backup_codes_hash` (lista di
  hash dei codici di recupero, ciascuno monouso)
- `created_at`, `last_login_at`

### `record`
Entità "canonica" di deduplicazione: rappresenta **un numero di telefono
univoco** e aggrega tutti gli annunci collegati.
- `id`
- `phone_encrypted` (AES-256-GCM), `phone_hmac` (indicizzato, univoco)
- `phone_country_hint`, `phone_display_masked` (es. `+39 3xx xxx xx89`,
  per visualizzazione senza decifrare a ogni richiesta)
- `canonical_advertisement_id` (FK verso `advertisement`, l'annuncio
  attualmente selezionato come rappresentativo)
- `first_seen_at`, `last_seen_at`, `advertisement_count`

### `advertisement`
Singolo annuncio scrapato da una fonte, prima della deduplicazione.
- `id`, `record_id` (FK verso `record`, valorizzato dopo la
  deduplicazione)
- `source_id` (FK verso `sources`), `external_id` (id/URL nella fonte
  originale, per idempotenza dello scraping)
- `raw_title`, `raw_description`, `city`, `age_declared`
- `normalized_phone_hmac` (ridondante rispetto a `record.phone_hmac`,
  utile per il matching prima ancora che il record sia creato/collegato)
- `scraped_at`, `source_published_at`, `is_active` (annuncio ancora
  presente sulla fonte all'ultimo run)

### `media`
Media (immagine/video) associato a un annuncio.
- `id`, `advertisement_id` (FK), `record_id` (FK, denormalizzato per
  query dirette)
- `storage_bucket`, `storage_key` (posizione su MinIO), `media_type`
  (`image` / `video`), `mime_type`, `file_size_bytes`
- `thumbnail_storage_key`
- `classification_status` (`pending` / `classified` / `failed`),
  `classification_label_current` (es. volto visibile, watermark
  presente, esplicito/non esplicito - tassonomia da definire in
  `PROGETTO.md`)
- `downloaded_at`

### `sources`
Configurazione delle fonti scrapate (uno o più connettori, vedi
`docs/SVILUPPO.md` per come aggiungerne uno).
- `id`, `code` (slug univoco, es. `escort_advisor`, `bakeca_incontri`,
  `moscarossa`, `megaescort`, `escortforumit`, `escortacom`,
  `rosa_rossa`, `torino_erotica`, `punterforum`)
- `display_name`, `base_url`, `is_active`
- `scrape_schedule_cron` (usato dallo scheduler/Celery Beat)
- `rate_limit_config` (JSON: richieste/minuto, backoff)
- `robots_txt_checked_at`, `tos_notes` (riferimento a verifica ToS/robots,
  vedi `PROGETTO.md`)

### `scrape_runs`
Storico dei run di scraping per fonte.
- `id`, `source_id` (FK), `started_at`, `finished_at`, `status`
  (`running` / `success` / `partial_failure` / `failed`)
- `advertisements_found`, `advertisements_new`, `advertisements_updated`

### `scrape_errors`
Errori occorsi durante un run (per debug/osservabilità, collegati a
Grafana/Loki tramite correlazione sui log).
- `id`, `scrape_run_id` (FK), `occurred_at`, `error_type`, `message`,
  `url` (pagina/annuncio che ha causato l'errore)

### `canonical_history`
Traccia ogni cambio di annuncio canonico per un `record`, per
trasparenza/audit sulla selezione deterministica.
- `id`, `record_id` (FK), `previous_advertisement_id`,
  `new_advertisement_id`, `changed_at`, `reason` (es. "nuovo annuncio più
  recente e più completo", regola applicata dall'algoritmo)

### `media_classification_history`
Storico delle rivalutazioni di classificazione di un media (utile quando
il classificatore viene aggiornato/ri-eseguito).
- `id`, `media_id` (FK), `classified_at`, `model_version`, `labels`
  (JSON), `confidence_scores` (JSON)

### `summary_versions`
Storico dei riepiloghi generati dall'AI per un record (permette di
tornare a una versione precedente e di tracciare quale modello/prompt li
ha generati).
- `id`, `record_id` (FK), `generated_at`, `model_provider`,
  `model_name`, `prompt_version`, `content` (testo del riepilogo),
  `is_current` (bool)

### `export_jobs`
Job di esportazione dati richiesti dagli utenti.
- `id`, `requested_by_user_id` (FK verso `users`), `filter_criteria`
  (JSON, gli stessi parametri di `/api/v1/search`), `format`
  (`csv` / `json` / `zip_with_media`)
- `status` (`pending` / `running` / `completed` / `failed`),
  `storage_key` (pacchetto risultante su MinIO), `expires_at`
  (per pulizia automatica via scheduler)
- `created_at`, `completed_at`

### `audit_log`
Traccia delle azioni sensibili per requisiti di sicurezza/GDPR.
- `id`, `user_id` (FK, nullable per azioni di sistema), `action` (es.
  `login`, `login_2fa_failed`, `export_created`, `export_downloaded`,
  `user_role_changed`, `source_created`)
- `target_type`, `target_id`, `metadata` (JSON), `ip_address`,
  `created_at`

## 3. Relazioni principali (riassunto)

```
sources 1───N advertisement N───1 record 1───N media
                    │                │
                    │                ├──1 canonical_history (storico)
                    │                └──1 summary_versions (storico)
                    │
                    └──N scrape_runs (via source_id) ──N scrape_errors

users 1───N export_jobs
users 1───N audit_log
media 1───N media_classification_history
```

Indici chiave attesi: `record.phone_hmac` (univoco), `advertisement.
source_id + external_id` (univoco, per idempotenza scraping),
`advertisement.normalized_phone_hmac`, `media.advertisement_id`,
`export_jobs.expires_at` (per il job di pulizia periodica). L'elenco
definitivo/eventuali indici aggiuntivi per query di ricerca sono da
finalizzare in fase di ottimizzazione (vedi `PROGETTO.md`).
