#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)
ENV_FILE=${1:-.env.production}
case "$ENV_FILE" in
  /*) ;;
  *) ENV_FILE="${PROJECT_DIR}/${ENV_FILE}" ;;
esac

set -a
. "$ENV_FILE"
set +a
cd "$PROJECT_DIR"

compose() {
  docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.production.yml "$@"
}

compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile
compose exec -T api python -c "from app.config import settings; assert settings.ENVIRONMENT == 'production'; print('configurazione production valida')"
compose exec -T api alembic current

echo "[verify] Attendo il certificato e l'endpoint HTTPS..."
curl --fail --silent --show-error --retry 24 --retry-delay 5 \
  "https://${APP_DOMAIN}/api/v1/healthz" >/dev/null
curl --fail --silent --show-error --retry 6 --retry-delay 2 \
  -H "Host: ${PUBLIC_IP}" "http://${PUBLIC_IP}/api/v1/healthz" >/dev/null

redirect_code=$(curl --silent --output /dev/null --write-out '%{http_code}' "http://${APP_DOMAIN}/")
case "$redirect_code" in
  301|302|307|308) ;;
  *) echo "[verify] ERRORE: il dominio HTTP non reindirizza a HTTPS ($redirect_code)" >&2; exit 1 ;;
esac

for service in api nginx caddy postgres redis minio worker-scraper worker-media worker-ai worker-exports scheduler; do
  running=$(compose ps --status running --services | grep -Fx "$service" || true)
  [ -n "$running" ] || { echo "[verify] ERRORE: servizio non in esecuzione: $service" >&2; exit 1; }
done

echo "[verify] Dominio HTTPS, accesso IP HTTP, migrazioni e servizi principali sono operativi."
echo "[verify] Controllare dall'esterno che 3000/9000/9001/9090/3100 risultino chiuse."
