# Sicurezza - Lavoro Esterno

Questo documento descrive il modello di sicurezza dell'applicazione:
autenticazione, autorizzazione, gestione segreti, cifratura dati e note
di conformità. Applicazione ad **accesso riservato**: nessuna
registrazione pubblica, tutti gli utenti sono creati da un Admin.

## 1. Autenticazione JWT

- Login con email + password (`/api/v1/auth/login`); password salvate
  con hash forte (es. bcrypt/argon2 lato backend, mai in chiaro né con
  hash reversibili).
- Alla riuscita del login vengono emessi:
  - **access token** JWT, vita breve (`JWT_ACCESS_TTL_MINUTES`,
    default 15 minuti), usato in `Authorization: Bearer` su ogni
    richiesta API.
  - **refresh token** JWT, vita lunga (`JWT_REFRESH_TTL_DAYS`,
    default 14 giorni), usato solo su `/api/v1/auth/refresh` per ottenere
    una nuova coppia di token senza richiedere nuovamente la password.
- Access e refresh token sono firmati con la stessa chiave simmetrica
  (`JWT_SECRET_KEY`) ma sono distinguibili tramite un claim `type` nel
  payload (`access`/`refresh`), verificato lato backend prima di onorare
  ciascuna richiesta: un access token non può essere usato su
  `/api/v1/auth/refresh` e viceversa.
- Logout (`/api/v1/auth/logout`) revoca il refresh token lato server
  (richiede tracciamento/blacklist dei refresh token attivi o rotazione
  con storicizzazione, da confermare in fase di implementazione backend).

## 2. 2FA TOTP

- **Obbligatoria per il ruolo Admin**, fortemente raccomandata per
  Operator (la policy esatta per Operator è da rivedere, vedi
  `PROGETTO.md`).
- Setup (`/api/v1/auth/2fa/setup` -> `/api/v1/auth/2fa/confirm`):
  1. Il server genera un segreto TOTP casuale e lo cifra a riposo
     (`users.totp_secret`).
  2. Viene restituito un QR code (URI standard `otpauth://totp/...`) da
     inquadrare con un'app authenticator (Google Authenticator, Authy,
     ecc.).
  3. L'utente conferma inserendo un codice a 6 cifre valido; solo a
     questo punto la 2FA viene attivata (`totp_enabled = true`).
  4. Il server genera un set di **backup codes monouso**, mostrati una
     sola volta all'utente e salvati solo come hash (`backup_codes_
     hash`): permettono l'accesso in caso di perdita del dispositivo
     authenticator.
- Login con 2FA attiva: dopo email+password, il client deve completare
  `/api/v1/auth/2fa/verify` con un codice TOTP (o un backup code) prima
  di ricevere i token definitivi (vedi flusso in `docs/API.md`).
- **Recovery account**: se un utente perde sia il dispositivo TOTP sia i
  backup codes, solo un Admin può resettare la 2FA dell'account
  (`PATCH /api/v1/admin/users/{user_id}` con azione di reset 2FA),
  operazione che va registrata in `audit_log`.

## 3. RBAC - 3 ruoli

| Ruolo | Permessi |
|---|---|
| **Admin** | Accesso completo: gestione utenti, gestione fonti (`sources`), configurazione, consultazione audit log, tutte le operazioni di Operator/Viewer. 2FA obbligatoria. |
| **Operator** | Ricerca/consultazione record, avvio manuale di run di scraping, richiesta export, riclassificazione media/riepiloghi. Nessun accesso a gestione utenti o configurazione di sistema. |
| **Viewer** | Solo lettura: ricerca e consultazione record/media/riepiloghi. Nessun avvio di operazioni (scraping, export, riclassificazione). |

L'applicazione dei permessi avviene lato backend (dependency FastAPI che
verifica `role` dal JWT ad ogni richiesta), mai solo lato frontend
(il frontend nasconde/disabilita funzionalità per UX, ma il backend è
l'unico enforcement point valido).

## 4. Gestione segreti

- **Nessun segreto va committato nel repository**: password, chiavi JWT,
  chiavi di cifratura, credenziali MinIO/Grafana vivono esclusivamente
  nel file `.env` locale/di ambiente (mai in `.env.example`, che contiene
  solo placeholder) e, in produzione, in un secrets manager dedicato
  (vedi `PROGETTO.md`, sezione Deploy).
- `.env` deve restare in `.gitignore`.
- Segreti diversi per ogni ambiente (dev/staging/produzione); nessuna
  condivisione di chiavi tra ambienti.
- Rotazione: `JWT_SECRET_KEY` può essere ruotata invalidando tutte le
  sessioni attive (access e refresh token in circolazione smettono di
  validare); `PHONE_ENCRYPTION_KEY` e
  `PHONE_HMAC_SECRET` richiedono invece una migrazione dati dedicata se
  ruotati (vedi `docs/DATABASE.md` e `.env.example`).

## 5. Cifratura dati sensibili

- Numero di telefono: cifrato AES-256-GCM a riposo, con hash
  HMAC-SHA256 separato per la ricerca/deduplicazione (dettagli in
  `docs/DATABASE.md`, §1).
- Segreto TOTP (`users.totp_secret`): cifrato a riposo con lo stesso
  meccanismo applicativo di cifratura simmetrica.
- Traffico in transito: TLS terminato a livello di reverse
  proxy/infrastruttura (vedi `PROGETTO.md`, Deploy, per la configurazione
  del certificato in produzione — non presente in questo setup di base).

## 6. Audit log

Ogni azione sensibile viene registrata nella tabella `audit_log`
(`docs/DATABASE.md`): login (riuscito/fallito), fallimenti 2FA, creazione
ed export di dati, modifiche a utenti e fonti. Consultabile da Admin via
`GET /api/v1/admin/audit-log`. L'audit log **non contiene mai** il numero
di telefono in chiaro.

## 7. Conformità e GDPR

Riferimento: **§21 del documento di progetto** (`lavoro-esterno-1-stack-
tecnico.pdf`) per i requisiti di conformità dettagliati concordati con il
cliente. Principi applicati nell'architettura:

- **Minimizzazione dei dati**: si raccolgono solo i campi necessari alla
  finalità dichiarata (deduplicazione annunci, non profilazione estesa);
  il numero di telefono è cifrato, non esposto in chiaro se non
  strettamente necessario nell'interfaccia autorizzata.
- **Retention configurabile**: i dati raccolti (annunci, media, log) non
  vanno conservati indefinitamente; la durata di retention per ciascuna
  categoria di dato è **da definire e rendere configurabile** (vedi
  `PROGETTO.md`), con job di pulizia periodici (analoghi a quello già
  previsto per `export_jobs.expires_at`).
- **Rispetto dei ToS/robots.txt delle fonti scrapate**: ogni connettore
  scraper deve essere validato legalmente prima dell'attivazione in
  produzione (verifica `robots.txt`, termini di servizio della fonte,
  eventuali basi giuridiche per il trattamento) — tracciato per fonte in
  `sources.robots_txt_checked_at` / `sources.tos_notes`. Questa
  validazione **non è automatizzabile** e richiede revisione
  legale/umana per ciascuna fonte (elenco completo in `PROGETTO.md`).
- **Diritti dell'interessato**: essendo dati relativi a persone fisiche
  (numeri di telefono), vanno predisposte procedure di cancellazione su
  richiesta e limitazione dell'accesso ai soli ruoli autorizzati (RBAC
  sopra). Le procedure operative complete sono da finalizzare con
  consulenza legale (vedi `PROGETTO.md`, sezione Sicurezza/GDPR).

> Questo documento descrive il disegno tecnico di sicurezza. La
> validazione legale/normativa completa (in particolare relativa allo
> scraping di dati personali da fonti terze) resta un'attività separata,
> tracciata come attività aperta in `PROGETTO.md`.
