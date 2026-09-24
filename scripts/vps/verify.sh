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

fail() {
  echo "[verify] ERRORE: $1" >&2
  exit 1
}

header_value() {
  awk -v wanted="$2" '
    BEGIN { IGNORECASE = 1 }
    index(tolower($0), tolower(wanted) ":") == 1 {
      sub(/^[^:]+:[[:space:]]*/, "")
      sub(/\r$/, "")
      print
      exit
    }
  ' "$1"
}

verify_asset() {
  asset_path=$1
  curl --fail --silent --show-error "https://${APP_DOMAIN}${asset_path}" >/dev/null || \
    fail "asset non raggiungibile dal dominio: ${asset_path}"
  curl --fail --silent --show-error -H "Host: ${PUBLIC_IP}" \
    "http://${PUBLIC_IP}${asset_path}" >/dev/null || \
    fail "asset non raggiungibile dall'ingresso IP: ${asset_path}"
}

compose exec -T caddy caddy validate --config /etc/caddy/Caddyfile
compose exec -T api python -c "from app.config import settings; assert settings.ENVIRONMENT == 'production'; print('configurazione production valida')"
compose exec -T api alembic current

echo "[verify] Attendo il certificato e l'endpoint HTTPS..."
curl --fail --silent --show-error --retry 24 --retry-delay 5 \
  "https://${APP_DOMAIN}/api/v1/healthz" >/dev/null
curl --fail --silent --show-error --retry 6 --retry-delay 2 \
  -H "Host: ${PUBLIC_IP}" "http://${PUBLIC_IP}/api/v1/healthz" >/dev/null

verify_dir=$(mktemp -d)
trap 'rm -rf "$verify_dir"' EXIT HUP INT TERM
curl --fail --silent --show-error --dump-header "$verify_dir/domain.headers" \
  --output "$verify_dir/domain.html" "https://${APP_DOMAIN}/"
curl --fail --silent --show-error --dump-header "$verify_dir/ip.headers" \
  --output "$verify_dir/ip.html" -H "Host: ${PUBLIC_IP}" "http://${PUBLIC_IP}/"

domain_csp=$(header_value "$verify_dir/domain.headers" Content-Security-Policy)
ip_csp=$(header_value "$verify_dir/ip.headers" Content-Security-Policy)
[ -n "$domain_csp" ] || fail "Content-Security-Policy assente sul dominio"
[ "$domain_csp" = "$ip_csp" ] || fail "dominio e IP non restituiscono la stessa CSP"
case "$domain_csp" in
  *unsafe-inline*) fail "la CSP contiene unsafe-inline" ;;
esac
for directive in "script-src 'self'" "script-src-attr 'none'" "style-src 'self'" \
  "style-src-attr 'none'" "font-src 'self'" "object-src 'none'" "base-uri 'none'"; do
  case "$domain_csp" in
    *"$directive"*) ;;
    *) fail "direttiva CSP mancante: $directive" ;;
  esac
done

[ -n "$(header_value "$verify_dir/domain.headers" Strict-Transport-Security)" ] || \
  fail "HSTS assente dal dominio HTTPS"
[ -z "$(header_value "$verify_dir/ip.headers" Strict-Transport-Security)" ] || \
  fail "HSTS non deve essere inviato dall'ingresso IP HTTP"

for html_file in "$verify_dir/domain.html" "$verify_dir/ip.html"; do
  grep -Eqi 'fonts\.(googleapis|gstatic)\.com' "$html_file" && \
    fail "HTML con riferimenti a Google Fonts"
  grep -Eqi '<style([[:space:]>])' "$html_file" && fail "HTML con blocco style inline"
  grep -Eqi '[[:space:]]style[[:space:]]*=' "$html_file" && fail "HTML con attributo style"
  if grep -Ei '<script' "$html_file" | grep -Eiv '<script[^>]*[[:space:]]src=' >/dev/null; then
    fail "HTML con script inline"
  fi
done

verify_asset "/theme-init.js"
for extension in css js woff2; do
  asset_file=$(compose exec -T frontend sh -c \
    "find /usr/share/nginx/html/assets -type f -name '*.${extension}' | head -n 1")
  [ -n "$asset_file" ] || fail "nessun asset .${extension} nel frontend"
  asset_path=${asset_file#/usr/share/nginx/html}
  verify_asset "$asset_path"
done

redirect_code=$(curl --silent --output /dev/null --write-out '%{http_code}' "http://${APP_DOMAIN}/")
case "$redirect_code" in
  301|302|307|308) ;;
  *) fail "il dominio HTTP non reindirizza a HTTPS ($redirect_code)" ;;
esac

for service in api nginx caddy postgres redis minio worker-scraper worker-media worker-ai worker-exports scheduler; do
  running=$(compose ps --status running --services | grep -Fx "$service" || true)
  [ -n "$running" ] || fail "servizio non in esecuzione: $service"
done

echo "[verify] CSP, HSTS, asset locali, dominio HTTPS, accesso IP HTTP, migrazioni e servizi principali sono operativi."
echo "[verify] Controllare dall'esterno che 3000/9000/9001/9090/3100 risultino chiuse."
