#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)
ENV_FILE=${1:-.env.production}
case "$ENV_FILE" in
  /*) ;;
  *) ENV_FILE="${PROJECT_DIR}/${ENV_FILE}" ;;
esac

sh "${SCRIPT_DIR}/preflight.sh" "$ENV_FILE"
cd "$PROJECT_DIR"

compose() {
  docker compose --env-file "$ENV_FILE" -f docker-compose.yml -f docker-compose.production.yml "$@"
}

# Su un aggiornamento effettua backup verificati prima di sostituire i processi.
# Al primo avvio i servizi dati non esistono ancora e questo blocco viene saltato.
if compose ps --status running --services 2>/dev/null | grep -Fx postgres >/dev/null; then
  echo "[deploy] Backup PostgreSQL precedente all'aggiornamento..."
  compose exec -T backup-postgres sh /scripts/backup-postgres.sh --once
  compose exec -T backup-postgres sh -c \
    'latest=$(ls -1t /backups/lavoro_esterno_*.sql.gz | head -n 1); test -n "$latest"; gzip -t "$latest"'
fi
if compose ps --status running --services 2>/dev/null | grep -Fx minio >/dev/null; then
  echo "[deploy] Replica MinIO precedente all'aggiornamento..."
  compose exec -T backup-minio sh /scripts/backup-minio.sh --once
fi

echo "[deploy] Build e avvio. I volumi non vengono rimossi."
compose pull --ignore-buildable
compose build --pull
compose up -d --remove-orphans

sh "${SCRIPT_DIR}/verify.sh" "$ENV_FILE"
echo "[deploy] Deployment completato: https://${APP_DOMAIN}"
