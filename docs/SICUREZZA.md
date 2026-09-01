# Sicurezza - Lavoro Esterno

Questo documento descrive il modello di sicurezza dell'applicazione:
autenticazione, autorizzazione, gestione segreti, cifratura dati e note
di conformità. Applicazione ad **accesso riservato**: nessuna
registrazione pubblica, tutti gli utenti sono creati da un Admin.

## 1. Autenticazione JWT

- Login con email + password (`POST /api/v1/auth/login`); password
  salvate con hash Argon2id (`app/security/password.py`), mai in chiaro
  né con hash reversibili. Policy di complessità minima (nessuna
  scadenza forzata, decisione di prodotto): lunghezza minima
  (`PASSWORD_MIN_LENGTH`, default 12), almeno 3 classi di caratteri su 4,
  non deve contenere l'email dell'utente né essere tra le password più
  comuni note (`validate_password_strength`), applicata alla creazione
  utente e a `POST /api/v1/auth/change-password`.
- Alla riuscita del login vengono emessi:
  - **access token** JWT, vita breve (`JWT_ACCESS_TTL_MINUTES`,
    default 15 minuti), usato in `Authorization: Bearer` su ogni
    richiesta API.
  - **refresh token** JWT, vita lunga (`JWT_REFRESH_TTL_DAYS`,
    default 14 giorni), usato solo su `POST /api/v1/auth/refresh` per
    ottenere una nuova coppia di token senza richiedere nuovamente la
    password.
- Access e refresh token sono firmati con la stessa chiave simmetrica
  (`JWT_SECRET_KEY`) ma sono distinguibili tramite un claim `type` nel
  payload (`access`/`refresh`), verificato lato backend prima di onorare
  ciascuna richiesta: un access token non può essere usato su
  `/api/v1/auth/refresh` e viceversa. Ogni token porta inoltre due claim
  aggiuntivi usati per la revoca (`app/security/jwt.py`,
  `app/security/deps.py`):
  - `jti`: identificatore univoco del singolo token, usato per la
    **blacklist puntuale** (Redis, `app/security/redis_client.py`) su
    `POST /api/v1/auth/logout` — revoca l'access token corrente e, se
    inviato nel body, il refresh token della stessa sessione.
  - `sst` ("security stamp"): snapshot di `users.security_stamp_at` al
    momento dell'emissione. Aggiornare questa colonna (cambio password,
    reset 2FA amministrativo) invalida **in blocco** tutti i token
    precedentemente emessi per l'utente, senza dover tracciare ogni
    singolo `jti` mai emesso — un token con `sst` non più corrispondente
    viene rifiutato sia da `get_current_user` sia da
    `POST /api/v1/auth/refresh`.
- **Rate limiting / lockout** (protezione brute-force, contatori Redis
  con prefisso `auth:`): `LOGIN_MAX_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES`
  (default 5 tentativi / 15 minuti) su `POST /auth/login`,
  `MFA_MAX_ATTEMPTS`/`MFA_LOCKOUT_MINUTES` sulla verifica del codice 2FA
  (`POST /auth/login-2fa`, `POST /auth/verify-2fa`). Oltre soglia, risposta
  `429` con `{"error_code": "too_many_attempts", "retry_after_seconds": N}`.

## 2. 2FA TOTP

- **Obbligatoria dal login per i ruoli Admin e Operator** (decisione di
  prodotto: nessun periodo di grazia). Un account con questi ruoli ma
  privo di 2FA riceve token validi solo per completare il setup: qualunque
  altro endpoint applicativo risponde `403`
  (`{"error_code": "mfa_setup_required"}`, enforcement in
  `app/security/deps.py:get_current_user`) finché non viene attivata.
  Lato frontend, `ProtectedRoute`/`AuthContext` reindirizzano
  automaticamente a `/2fa-setup` (`TwoFactorSetupPage.tsx`) in questo
  stato.
- Setup (`POST /api/v1/auth/setup-2fa` -> `POST /api/v1/auth/verify-2fa`):
  1. Il server genera un segreto TOTP casuale e lo cifra a riposo
     (`users.totp_secret_encrypted`, stesso schema AES-256-GCM del
     numero di telefono).
  2. Viene restituito un QR code (URI standard `otpauth://totp/...`) da
     inquadrare con un'app authenticator (Google Authenticator, Microsoft
     Authenticator, ecc.).
  3. L'utente conferma inserendo un codice a 6 cifre valido; solo a
     questo punto la 2FA viene attivata (`totp_enabled = true`).
  4. Il server genera un set di 10 **backup codes monouso**, mostrati una
     sola volta all'utente e salvati solo come hash Argon2
     (`backup_codes_hash`): permettono l'accesso in caso di perdita del
     dispositivo authenticator.
- Login con 2FA attiva: dopo email+password, il client deve completare
  `POST /api/v1/auth/login-2fa` con un codice TOTP (o un backup code)
  prima di ricevere i token definitivi (vedi flusso in `docs/API.md`).
- **Rotazione backup codes**: rigenerazione manuale via
  `POST /api/v1/auth/2fa/backup-codes/regenerate` (richiede ri-verifica
  di un codice TOTP corrente). Rigenerazione **automatica** quando
  l'utente consuma l'ultimo backup code rimasto durante il login: i 10
  nuovi codici sono restituiti una sola volta in `new_backup_codes` sulla
  risposta di `login-2fa`, mostrati dal frontend in un modale bloccante
  prima di proseguire — l'utente non resta mai silenziosamente senza via
  di recovery.
- **Recovery account**: se un utente perde sia il dispositivo TOTP sia i
  backup codes, solo un Admin può resettare la 2FA dell'account
  (`POST /api/v1/admin/users/{user_id}/reset-2fa`, richiede
  `require_admin_with_2fa`), operazione registrata in `audit_log`
  (azione `reset_2fa`) che aggiorna anche `security_stamp_at` (revoca di
  ogni token residuo dell'utente). Non esiste un servizio email nel
  progetto: la recovery è deliberatamente admin-driven, non self-service.
  Dopo il reset l'utente rifà il setup obbligatorio al prossimo login
  (stesso enforcement del punto precedente).

## 3. RBAC - 3 ruoli

| Ruolo | Permessi |
|---|---|
| **Admin** | Accesso completo: gestione utenti, gestione fonti (`sources`), configurazione, consultazione audit log, tutte le operazioni di Operator/Viewer. 2FA obbligatoria dal login. |
| **Operator** | Ricerca/consultazione record, avvio manuale di run di scraping, richiesta export, riclassificazione media/riepiloghi. Nessun accesso a gestione utenti o configurazione di sistema. 2FA obbligatoria dal login (stessa policy di Admin). |
| **Viewer** | Solo lettura: ricerca e consultazione record/media/riepiloghi. Nessun avvio di operazioni (scraping, export, riclassificazione). 2FA facoltativa. |

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

### Provider AI e media sensibili

- Prima della Responses API vengono rimossi telefoni e URL anche dal testo
  libero; immagini, URL originali e numeri cifrati non lasciano il sistema.
  I riferimenti `source-N` restituiti dal modello sono rimappati localmente.
- Le richieste usano `store=false`. Secondo i [controlli dati OpenAI](https://developers.openai.com/api/docs/guides/your-data), i dati API non
  vengono usati per training salvo opt-in; i log di abuse monitoring possono
  essere conservati fino a 30 giorni. Zero Data Retention richiede idoneità e
  approvazione separate e non va presunta da questa configurazione.
- I media `unclassified`, con elaborazione fallita o revisione richiesta
  sono sempre sensibili nella UI. `possibleMinorReview` non è una stima di
  età: segnala soltanto la coesistenza prudenziale di nudità e volto.
- La rimozione watermark è disabilitata per default, configurabile solo da
  Admin con riferimento autorizzativo e regioni esplicite; originali e audit
  vengono conservati.

> Questo documento descrive il disegno tecnico di sicurezza. La
> validazione legale/normativa completa (in particolare relativa allo
> scraping di dati personali da fonti terze) resta un'attività separata,
> tracciata come attività aperta in `PROGETTO.md`.
