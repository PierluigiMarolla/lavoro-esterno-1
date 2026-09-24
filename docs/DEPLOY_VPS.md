# Deploy su VPS

Questa procedura pubblica l'applicazione tramite Caddy mantenendo database,
Redis, MinIO, Ollama e osservabilita fuori da Internet. Il dominio usa HTTPS
automatico; l'IP pubblico espone anche HTTP per scelta esplicita, con un avviso
visibile nell'interfaccia.

L'immagine edge viene costruita da Caddy 2.11.4 con toolchain e dipendenze Go
corrette, anziche usare un tag upstream obsoleto rispetto al database CVE. La
CI e il deploy devono continuare a bloccare immagini con rilievi High/Critical.

## 1. Prerequisiti

- VPS Ubuntu/Debian con almeno 4 vCPU, 16 GB RAM e circa 40 GB liberi;
- Docker Engine e plugin Docker Compose 2.24 o successivo;
- dominio con record `A` diretto all'IPv4 della VPS;
- porte TCP 80/443 raggiungibili; UDP 443 e consigliata per HTTP/3;
- porta SSH nota e consentita prima di attivare il firewall.

Il modello `gemma4:e2b` richiede un download iniziale di circa 7,2 GB. I dati
del modello e i certificati Caddy restano in volumi Docker persistenti.

## 2. Configurazione

```bash
cp .env.production.example .env.production
chmod 600 .env.production
```

Sostituire dominio, IP, email ACME e tutti i valori `REPLACE_*`. Usare password
esadecimali per PostgreSQL, cosi possono essere copiate senza URL-encoding nelle
due connection string:

```bash
openssl rand -hex 32       # password PostgreSQL/MinIO/Grafana e HMAC
openssl rand -base64 64    # JWT_SECRET_KEY
openssl rand -base64 32    # ripetere 4 volte per le chiavi AES, valori diversi
```

`MINIO_PUBLIC_ENDPOINT` deve essere `https://APP_DOMAIN`; l'endpoint interno
rimane `minio:9000` con `MINIO_SECURE=false`. Non sostituirlo con l'IP.

Eseguire il controllo non distruttivo:

```bash
sh scripts/vps/preflight.sh .env.production
```

Il controllo blocca placeholder, DNS incoerente, IP non pubblico, Compose
obsoleto e configurazioni che renderebbero inutilizzabili URL firmati o login.

## 3. Firewall e avvio

Esempio UFW, adattando la porta SSH se non e 22:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

Avvio o aggiornamento:

```bash
sh scripts/vps/deploy.sh .env.production
```

Lo script esegue il preflight, crea e verifica un dump PostgreSQL e la replica
MinIO quando aggiorna uno stack esistente, costruisce le immagini, applica le
migrazioni tramite il servizio `migrate` e verifica HTTPS, accesso IP e worker.
Non esegue mai `docker compose down -v`.

Per il primo Admin:

```bash
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml \
  exec api python -m app.scripts.create_admin \
  --email admin@example.com --password 'PASSWORD-FORTE'
```

Aprire `https://APP_DOMAIN`, completare la 2FA e conservare i codici di backup.
`http://PUBLIC_IP` funziona, ma non cifra credenziali, token o dati e mostra un
avviso permanente. Deve essere usato solo quando strettamente necessario.

## 4. Servizi amministrativi

Le porte operative ascoltano soltanto sul loopback della VPS. Per accedere da
un computer amministrativo usare tunnel SSH:

```bash
ssh -L 3000:127.0.0.1:3000 \
    -L 9001:127.0.0.1:9001 \
    -L 9090:127.0.0.1:9090 user@APP_DOMAIN
```

Poi usare `http://localhost:3000` (Grafana), `http://localhost:9001` (MinIO) e
`http://localhost:9090` (Prometheus). Loki `3100` e MinIO API `9000` possono
essere inoltrati allo stesso modo solo per diagnosi mirate.

## 5. Diagnostica, aggiornamento e rollback

```bash
sh scripts/vps/verify.sh .env.production
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml ps
docker compose --env-file .env.production \
  -f docker-compose.yml -f docker-compose.production.yml logs -f caddy api
```

Per aggiornare: conservare una copia di `.env.production`, acquisire il nuovo
codice e rieseguire `deploy.sh`. Per rollback tornare alla revisione applicativa
precedente e rieseguire lo stesso script. Non effettuare downgrade Alembic senza
una procedura specifica e non cancellare volumi. Se una migrazione fallisce,
`migrate` impedisce automaticamente l'avvio di API e worker incompatibili.

I backup inclusi restano sullo stesso host: configurare una copia cifrata
off-site e provarne periodicamente il ripristino prima del go-live definitivo.

## 6. Content Security Policy e risorse frontend

Il dominio HTTPS e l'ingresso HTTP tramite IP applicano la stessa CSP
restrittiva. Script, stili, font, chiamate API, immagini e video sono ammessi
soltanto dalla stessa origine; non sono presenti `unsafe-inline` o wildcard
`https:`. HSTS viene inviato esclusivamente dal dominio HTTPS.

Inter, JetBrains Mono e Material Symbols sono inclusi nel bundle come WOFF2.
Le relative licenze vengono copiate in `dist/licenses` durante il build. Anche
lo script che determina il tema iniziale è servito localmente come
`/theme-init.js`, prima del bundle React.

La verifica completa è inclusa nel normale deploy:

```bash
sh scripts/vps/verify.sh .env.production
```

Lo script confronta la CSP dei due ingressi, controlla HSTS, rifiuta
`unsafe-inline` e prova HTML, CSS, JavaScript, tema e font locali. Per una
diagnosi manuale:

```bash
curl -sSI https://APP_DOMAIN/ | grep -iE 'content-security-policy|strict-transport-security'
curl -sSI -H 'Host: PUBLIC_IP' http://PUBLIC_IP/ | grep -iE 'content-security-policy|strict-transport-security'
```

La seconda risposta deve avere la stessa CSP ma non deve contenere HSTS. Dopo
un aggiornamento del frontend eseguire sempre `npm run build`: il controllo
`check:csp` blocca script/stili inline, URL Google e risorse CSS remote.
