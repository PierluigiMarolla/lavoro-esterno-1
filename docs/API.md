# API - Lavoro Esterno

Tutte le rotte applicative sono servite sotto il prefisso `/api/v1/`
dall'API FastAPI e sono raggiungibili in produzione tramite il reverse
proxy nginx (`http(s)://<host>/api/v1/...`).

> **Documentazione interattiva**: la lista completa ed esatta di ogni
> endpoint (schema richiesta/risposta, codici di errore, esempi) è
> generata automaticamente da FastAPI ed è disponibile su `/docs`
> (Swagger UI) e `/openapi.json` (schema OpenAPI grezzo). Questo
> documento descrive le **aree funzionali** e lo scopo di ciascun gruppo
> di rotte, da usare come mappa di orientamento; per i dettagli tecnici
> fare sempre riferimento a `/docs`.

## Area `auth` - autenticazione e sessione

| Metodo | Path | Scopo |
|---|---|---|
| POST | `/api/v1/auth/login` | Prima fase: verifica email + password. Se l'utente NON ha 2FA attiva emette subito `access_token`/`refresh_token`/`user` con `status: "authenticated"`; se ce l'ha, risponde `status: "mfa_required"` e un `mfa_token` effimero (nessun token di accesso). |
| POST | `/api/v1/auth/login-2fa` | Seconda fase (solo utenti con 2FA attiva): scambia `mfa_token` + codice TOTP a 6 cifre (o un backup code) con `access_token`/`refresh_token`/`user`. |
| POST | `/api/v1/auth/refresh` | Scambia un refresh token valido con una nuova coppia access/refresh token. |
| GET | `/api/v1/auth/me` | Restituisce profilo, ruolo (Admin/Operator/Viewer) e stato 2FA dell'utente autenticato (richiede `Authorization: Bearer`). |
| POST | `/api/v1/auth/setup-2fa` | Avvia l'attivazione della 2FA per l'utente corrente: genera segreto TOTP, QR code (base64) e i backup codes monouso, mostrati una sola volta. |
| POST | `/api/v1/auth/verify-2fa` | Conferma l'attivazione 2FA fornendo un primo codice TOTP valido generato dall'app authenticator; solo dopo questa chiamata `totp_enabled` diventa `true`. |
| POST | `/api/v1/auth/logout` | Logout lato server: registra l'evento in `audit_log` e risponde `204`. I JWT restano stateless (nessuna vera revoca del token, vedi nota sotto). |

I JWT sono stateless a scadenza breve (access) / media (refresh):
`POST /auth/logout` non revoca davvero il token già emesso, si limita a
tracciare l'evento — vedi `docs/SICUREZZA.md` per la nota sulla
revoca/blacklist dei refresh token, ancora da implementare.

## Area `dashboard` - viste aggregate per la home

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/dashboard/kpis` | KPI aggregati (totale record, fonti attive, nuovi record oggi, errori di scraping, export attivi), con delta/percentuali calcolati per confronto tra finestre temporali adiacenti (nessuno storico snapshot dedicato: vedi commenti in `app/api/v1/dashboard.py`). |
| GET | `/api/v1/dashboard/scraping-activity` | Run di scraping più recenti (`scrape_runs`) joinati con la fonte. |
| GET | `/api/v1/dashboard/source-health` | Conteggio fonti per stato, rimappato sul vocabolario `healthy`/`rateLimited`/`error` (vedi `app/services/source_health.py`). |
| GET | `/api/v1/dashboard/activity` | Attività recente, derivata da `audit_log` (copre solo le azioni esplicitamente audit-loggate, non ogni evento di sistema). |

### Esempio di flusso login + 2FA

1. `POST /api/v1/auth/login` con `{ "email": ..., "password": ... }`.
2. Se l'utente ha la 2FA attiva, la risposta ha `status: "mfa_required"` e un
   campo `mfa_token` (token effimero, non utilizzabile come access token).
3. Il client chiede all'utente il codice a 6 cifre dell'app authenticator e
   chiama `POST /api/v1/auth/login-2fa` con
   `{ "mfa_token": ..., "code": "123456" }` (accetta anche un backup code
   monouso al posto del codice TOTP).
4. In caso di successo la risposta contiene `status: "authenticated"`,
   `access_token` (breve durata, vedi `JWT_ACCESS_TTL_MINUTES`),
   `refresh_token` (durata più lunga, vedi `JWT_REFRESH_TTL_DAYS`) e
   `user` (id/email/name/role/mfa_enabled/status), da usare rispettivamente
   come `Authorization: Bearer <access_token>` e per il rinnovo su
   `/api/v1/auth/refresh`. Nota: `user.name` e `user.status` sono derivati
   (email/`is_active`), non hanno colonne dedicate — vedi `UserPublic` in
   `backend/app/schemas/auth.py`.

## Area `search` - ricerca e consultazione

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/search` | Ricerca full-text/filtrata sui record consolidati (per città, età, fonte, intervallo date, presenza media, ecc.). |
| GET | `/api/v1/search/phone` | Ricerca diretta per numero di telefono (calcola l'HMAC lato server e cerca sull'indice, non richiede il numero in chiaro nel DB). |
| GET | `/api/v1/search/suggestions` | Suggerimenti/autocomplete su città, fonti, tag ricorrenti. |

## Area `records` - record consolidati e storico

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/records/search` | Ricerca paginata di record con filtri combinabili (`phone`, `source`, `status`, `date_from`, `date_to`, `page`, `page_size`). Il filtro `phone` cerca per hash esatto solo se il valore digitato sembra un numero completo (vedi `app/services/record_search.py`: non esiste ricerca a prefisso su un dato cifrato/hashato). |
| POST | `/api/v1/records/search` | Legacy: lookup esatto di un record dato un numero di telefono completo (hash di lookup). Non usato dal frontend attuale, mantenuto per compatibilità. |
| GET | `/api/v1/records/{record_id}` | Overview di un record per la UI: titolo/descrizione dell'annuncio canonico, confidence, conteggio fonti/occorrenze, status. |
| GET | `/api/v1/records/{record_id}/occurrences` | Tutti gli annunci (`advertisement`) collegati al record, con flag `isCanonical`. |
| GET | `/api/v1/records/{record_id}/media` | Media associati agli annunci del record, con classificazione (media non ancora classificato è trattato come "explicit" per default fail-safe). |
| GET | `/api/v1/records/{record_id}/history` | Storico unificato: unione di `canonical_history`, `media_classification_history` e `audit_log` filtrati per il record, ordinati per data. |
| GET | `/api/v1/records/{record_id}/ai-summary` | Ultima versione del riepilogo AI (`summary_versions`); risponde `204` se non è mai stato generato. |
| GET | `/api/v1/records/{record_id}/ai-summary/versions` | Storico COMPLETO delle versioni (non solo l'ultima), più recente prima — per il selettore storico in `RecordAiSummaryTab.tsx`. |
| POST | `/api/v1/records/{record_id}/ai-summary/regenerate` | Crea un job persistente e risponde `202` con `SummaryGenerationJobRead`; il worker usa OpenAI Responses/Structured Outputs. Riservato ad Admin/Operator. |
| GET | `/api/v1/records/{record_id}/ai-summary/jobs/{job_id}` | Stato asincrono `pending`, `processing`, `completed` o `failed`, versione risultante, cache hit ed errore sicuro. |

## Area `sources` - gestione fonti scrapate

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/sources` | Elenco delle fonti configurate: `code` (slug), `status`, `priority`, `lastRunAt`, `itemsLast24h`, `errorRate`, `consecutiveFailures`, `hasScrapeConfig` calcolati/letti da `scrape_runs`/`Source` (query N+1 accettata per il numero di fonti atteso, vedi commento in `app/api/v1/sources.py`); `country` è un placeholder fisso (`"N/D"`), nessuna colonna dedicata nel modello. |
| GET | `/api/v1/sources/summary` | Conteggio fonti per stato (`total`/`active`/`degraded`/`offline`). |
| GET | `/api/v1/sources/{source_id}` | Dettaglio di una fonte, incluso `scrapeConfig` completo (assente da `GET /sources`, che espone solo il booleano `hasScrapeConfig`) — usato per precompilare il form "Edit configuration". |
| POST | `/api/v1/sources` | Crea una fonte (solo Admin). Accetta `scrapeConfig` e `watermarkRemoval`; quest'ultimo richiede riferimento autorizzativo e almeno una regione normalizzata se abilitato. |
| PATCH | `/api/v1/sources/{source_id}` | Modifica `name`/`baseUrl`/`priority`/`scrapeConfig`/`watermarkRemoval` (solo Admin). Non permette di cambiare `slug`. |
| DELETE | `/api/v1/sources/{source_id}` | Rimuove una fonte (solo Admin). 409 se esistono `advertisement` collegati (storico preservato). |
| POST | `/api/v1/sources/{source_id}/check-robots` | Verifica live il `robots.txt` pubblico della fonte usando lo stesso User-Agent configurato per lo scan — nessun altro contenuto scaricato. Nessuna restrizione di ruolo oltre l'autenticazione. |
| POST | `/api/v1/sources/{source_id}/test-config` | Prova `scrapeConfig` su UN solo annuncio reale (non salvato su DB): utile per verificare i selettori prima di un run reale. Richiede Admin/Operator (esegue richieste HTTP reali verso la fonte). |
| GET | `/api/v1/sources/{source_id}/runs` | Storico dei run di scraping (`scrape_runs`) per la fonte, con gli errori di ciascun run annidati (`scrape_errors`) — drill-down per la pagina Sources. Sola lettura, nessuna restrizione di ruolo. |
| POST | `/api/v1/sources/{source_id}/pause` | Mette in pausa una fonte (`enabled=false`, status di salute invariato). Riservato ad Admin/Operator. |
| POST | `/api/v1/sources/{source_id}/disable` | Disabilita definitivamente una fonte (`enabled=false`, `status="offline"`). Riservato ad Admin/Operator. |
| POST | `/api/v1/sources/{source_id}/scan` | Accoda un task di scraping on-demand per la fonte (Celery). Se `scrapeConfig` è impostato, esegue DAVVERO lo scraping (motore generico); altrimenti nessuna azione reale (fonte registrata come classe Python stub, vedi `app/scrapers/registry.py`). |

### Motore di scraping generico (`scrapeConfig`)

Vedi `PROGETTO.md` § 4 e `docs/DATABASE.md` § "Motore di scraping
generico" per il razionale completo. Struttura di `scrapeConfig` (sia in
`POST`/`PATCH /sources` sia nella risposta di `GET /sources/{id}`):

```json
{
  "startUrls": ["https://example.com/listing"],
  "adLinkSelector": "a.ad-card",
  "nextPageSelector": "a.pagination-next",
  "maxPages": 5,
  "maxAdsPerRun": 200,
  "rateLimitSeconds": 2,
  "fetchMode": "http",
  "userAgent": "CustomScraper/2.0",
  "solveCloudflare": false,
  "blockWebrtc": false,
  "hideCanvas": false,
  "realChrome": false,
  "blockAds": false,
  "proxy": null,
  "waitSelector": null,
  "waitMs": null,
  "fields": {
    "phone": { "selector": ".ad-phone", "attribute": "text" },
    "title": { "selector": "h1.ad-title", "attribute": "text" },
    "images": { "selector": ".gallery img", "attribute": "src", "multiple": true }
  }
}
```

Vincoli validati lato server, non aggirabili: il campo `phone` è
obbligatorio in `fields` (senza telefono un annuncio non può essere
collegato a nessun Record); `rateLimitSeconds` ha un minimo di 1 secondo;
`maxPages`/`maxAdsPerRun` hanno un tetto massimo. Il motore usa Scrapling
con `fetchMode: "http"` di default; `"dynamic"` abilita il browser headless
per contenuti generati via JavaScript, `"stealth"` abilita le opzioni
anti-bot di Scrapling configurate sulla fonte. `renderJs` resta accettato
per compatibilità e, se `fetchMode` manca, equivale a `"dynamic"`. Il
motore rispetta sempre `robots.txt`. `userAgent` è opzionale e, se assente,
usa il default `app/scrapers/base.py:Scraper.user_agent`.

Una fonte può essere creata senza `scrapeConfig` (`POST /sources` con solo
`name`/`slug`/`baseUrl`) e configurata in un secondo momento via `PATCH
/sources/{id}` quando si decide di attivarne lo scraping reale (previa
verifica ToS/robots.txt per quella fonte specifica) — finché resta senza
configurazione, ogni tentativo di scan fallisce esplicitamente.

## Area `media` - gestione media e classificazione

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/media/{media_id}` | Metadati, segnali safety, processing/review state e URL presigned original/display/thumbnail. |
| GET | `/api/v1/media/by-advertisement/{advertisement_id}` | Elenco media di un annuncio con lo stesso contratto esteso. |
| POST | `/api/v1/media/{media_id}/review` | Override manuale `safe`/`explicit` con note, history e audit. Solo Admin/Operator. |
| POST | `/api/v1/media/{media_id}/reprocess` | Reimposta un media fallito/pregresso e accoda la pipeline media; risposta `202`. Solo Admin/Operator. |

Gli URL MinIO sono firmati per pochi minuti e costruiti usando
`MINIO_PUBLIC_ENDPOINT`; non vengono più esposte chiavi oggetto o URL
placeholder. Media `unclassified`, falliti o con `reviewStatus=required`
devono essere presentati dalla UI come sensibili.

## Area `exports` - esportazione dati

| Metodo | Path | Scopo |
|---|---|---|
| POST | `/api/v1/exports` | Crea un job di esportazione (`type` + `record_ids` e/o `filters`) -> record in `export_jobs`, stato iniziale `pending`. Riservato ad Admin/Operator. |
| GET | `/api/v1/exports` | Storico dei job di esportazione (i più recenti), con `requestedBy`/`progressPct`/`recordCount`/`downloadUrl` calcolati. Riservato ad Admin/Operator. |
| POST | `/api/v1/exports/{job_id}/retry` | Reimposta un job `failed` a `pending`. |
| GET | `/api/v1/exports/{job_id}/download` | URL di download del pacchetto. **TODO**: la generazione reale del pacchetto (worker + upload MinIO) non è implementata; risponde `409` finché `object_key` non è valorizzato, altrimenti un URL placeholder verso l'endpoint MinIO configurato (non ancora un presigned URL vero). |

### Esempio di flusso export

1. `POST /api/v1/exports` con i criteri di ricerca (stessi filtri di
   `/api/v1/search`) e il formato desiderato (es. CSV + media, o solo
   JSON). Risposta: `{ "job_id": "...", "status": "pending" }`.
2. Il job viene eseguito in background (worker, coda dedicata o `media`
   a seconda dell'implementazione finale, vedi `PROGETTO.md`).
3. Il client fa polling su `GET /api/v1/exports/{job_id}` finché
   `status` non è `completed` (o `failed`, con dettaglio errore).
4. A completamento, `GET /api/v1/exports/{job_id}/download` restituisce
   il pacchetto zip (contenente manifest con provenienza dei dati e
   media inclusi) da uno storage temporaneo su MinIO, con scadenza.

## Area `admin` - amministrazione

| Metodo | Path | Scopo |
|---|---|---|
| GET | `/api/v1/admin/users` | Elenco utenti (solo Admin). `name`/`lastLoginAt` sono approssimati (nessuna colonna dedicata nel modello `User`, vedi `app/schemas/admin.py:AdminUserRead`). |
| POST | `/api/v1/admin/users` | Creazione utente con ruolo (Admin/Operator/Viewer). Richiede Admin con 2FA attiva. Risponde con `AdminUserRead` (camelCase, coerente col resto dell'area — bug corretto: prima rispondeva con `UserRead` snake_case, forma diversa da `GET`/`PATCH`/`.../suspend`). |
| PATCH | `/api/v1/admin/users/{user_id}` | Modifica il ruolo di un utente. Richiede Admin con 2FA attiva. |
| POST | `/api/v1/admin/users/{user_id}/suspend` | Sospende un utente (`is_active=false`), impedendo nuovi login. Richiede Admin con 2FA attiva. |
| POST | `/api/v1/admin/users/{user_id}/reset-2fa` | Recovery account: disattiva la 2FA dell'utente (nessun servizio email nel progetto per un reset self-service), che dovrà rifare il setup obbligatorio al prossimo login. Risponde `{ id, mfa_enabled }` (snake_case, NON CamelModel — mappato esplicitamente in `frontend/src/api/admin.ts:resetAdminUserTwoFactor`, stesso stile di `auth.ts`). Richiede Admin con 2FA attiva. |
| GET | `/api/v1/admin/audit-log` | Consultazione dell'audit log (azioni sensibili: login/logout, export, modifiche utenti/fonti, rigenerazione riepilogo AI...). Solo Admin. |
| GET | `/api/v1/admin/system/health` | Stato aggregato dei componenti (DB, Redis, MinIO, ultimo run scheduler). *(Non ancora implementato.)* |

## Convenzioni generali

- Autenticazione via header `Authorization: Bearer <access_token>` su
  tutte le rotte tranne `auth/login` e i primi due passi della 2FA.
- Autorizzazione RBAC a 3 livelli (Admin/Operator/Viewer): il dettaglio
  dei permessi per ruolo è descritto in `docs/SICUREZZA.md`.
- Paginazione basata su `limit`/`offset` (o cursore, da confermare in
  fase di implementazione) sugli endpoint che restituiscono liste.
- Tutte le risposte di errore seguono lo schema standard di FastAPI
  (`detail`), consultabile nello schema OpenAPI su `/docs`.
