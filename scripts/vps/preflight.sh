#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "${SCRIPT_DIR}/../.." && pwd)
ENV_FILE=${1:-.env.production}
case "$ENV_FILE" in
  /*) ;;
  *) ENV_FILE="${PROJECT_DIR}/${ENV_FILE}" ;;
esac

fail() { echo "[preflight] ERRORE: $*" >&2; exit 1; }
warn() { echo "[preflight] AVVISO: $*" >&2; }
require_command() { command -v "$1" >/dev/null 2>&1 || fail "comando mancante: $1"; }

require_command docker
require_command curl
require_command getent
require_command python3
[ -f "$ENV_FILE" ] || fail "file ambiente non trovato: $ENV_FILE"

if grep -Eq '(^|=)(REPLACE_|change-me|dev-insecure)' "$ENV_FILE"; then
  fail "il file ambiente contiene ancora placeholder o segreti di sviluppo"
fi

set -a
# Il file e amministrato dal proprietario della VPS e deve contenere soltanto
# assegnazioni KEY=VALUE. Il controllo permessi sottostante limita l'esposizione.
. "$ENV_FILE"
set +a

for name in APP_DOMAIN PUBLIC_IP PUBLIC_BASE_URL ACME_EMAIL ALLOWED_HOSTS CORS_ORIGIN; do
  eval "value=\${$name:-}"
  [ -n "$value" ] || fail "variabile obbligatoria assente: $name"
done
[ "${APP_ENV_FILE:-}" = ".env.production" ] || fail "APP_ENV_FILE deve valere .env.production"
[ "${ENVIRONMENT:-}" = "production" ] || fail "ENVIRONMENT deve valere production"
[ "${ALLOW_INSECURE_IP_ACCESS:-}" = "true" ] || fail "ALLOW_INSECURE_IP_ACCESS deve valere true"
[ "${PUBLIC_BASE_URL%/}" = "https://${APP_DOMAIN}" ] || fail "PUBLIC_BASE_URL non coincide con APP_DOMAIN"
[ "${MINIO_PUBLIC_ENDPOINT%/}" = "${PUBLIC_BASE_URL%/}" ] || fail "MINIO_PUBLIC_ENDPOINT non coincide con PUBLIC_BASE_URL"

python3 - "$PUBLIC_IP" <<'PY'
import ipaddress, sys
address = ipaddress.ip_address(sys.argv[1])
if not address.is_global:
    raise SystemExit("[preflight] ERRORE: PUBLIC_IP non e un indirizzo pubblico instradabile")
PY

resolved=$(getent ahostsv4 "$APP_DOMAIN" | awk '{print $1}' | sort -u)
echo "$resolved" | grep -Fx "$PUBLIC_IP" >/dev/null 2>&1 \
  || fail "il DNS A di ${APP_DOMAIN} non contiene ${PUBLIC_IP} (risultato: ${resolved:-nessuno})"

mode=$(stat -c '%a' "$ENV_FILE" 2>/dev/null || true)
case "$mode" in
  600|400) ;;
  *) warn "proteggi i segreti con: chmod 600 $ENV_FILE (permessi attuali: ${mode:-sconosciuti})" ;;
esac

compose_version=$(docker compose version --short 2>/dev/null || true)
[ -n "$compose_version" ] || fail "Docker Compose plugin non disponibile"
compose_major=$(printf '%s' "$compose_version" | sed 's/^v//' | cut -d. -f1)
[ "$compose_major" -ge 2 ] 2>/dev/null || fail "Docker Compose 2.24 o superiore e richiesto"
if [ "$compose_major" -eq 2 ]; then
  compose_minor=$(printf '%s' "$compose_version" | sed 's/^v//' | cut -d. -f2)
  [ "$compose_minor" -ge 24 ] || fail "Docker Compose 2.24 o superiore e richiesto"
fi

cd "$PROJECT_DIR"
docker compose --env-file "$ENV_FILE" \
  -f docker-compose.yml -f docker-compose.production.yml config --quiet

memory_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
[ "$memory_kb" -ge 16000000 ] || warn "RAM inferiore a 16 GB: Gemma/Ollama puo essere lento o terminato per memoria"
disk_kb=$(df -Pk "$PROJECT_DIR" | awk 'NR==2 {print $4}')
[ "$disk_kb" -ge 40000000 ] || warn "spazio libero inferiore a circa 40 GB"

if command -v ss >/dev/null 2>&1; then
  for port in 80 443; do
    if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
      warn "porta $port gia in ascolto; e normale solo se appartiene al Caddy di questo progetto"
    fi
  done
fi

echo "[preflight] Configurazione valida, DNS coerente e prerequisiti presenti."
