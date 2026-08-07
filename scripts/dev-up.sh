#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
ENV_FILE=${HYAC_ENV_FILE:-"$REPO_ROOT/.env.dev"}
COMPOSE_FILE="$REPO_ROOT/docker-compose.dev.yml"
WAIT_TIMEOUT=${HYAC_WAIT_TIMEOUT:-180}
CHECK_ONLY=false

usage() {
  cat <<'EOF'
Usage: ./scripts/dev-up.sh [--check]

  --check  Validate local development prerequisites without building or starting services.
EOF
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command is missing: $1"
}

resolved_environment_value() {
  local key=$1
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --environment |
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; exit }'
}

verify_certificate() {
  local cert="$REPO_ROOT/traefik/certs/dev-cert.pem"
  local key="$REPO_ROOT/traefik/certs/dev-key.pem"
  local ca_root

  [[ -f "$cert" ]] || fail "Missing $cert. Generate it with mkcert for the documented localhost endpoints."
  [[ -f "$key" ]] || fail "Missing $key. Generate it with mkcert for the documented localhost endpoints."

  ca_root=$(mkcert -CAROOT)
  [[ -f "$ca_root/rootCA.pem" ]] || fail "mkcert CA is not initialized. Run: mkcert -install"
  openssl verify -CAfile "$ca_root/rootCA.pem" "$cert" >/dev/null ||
    fail "Development certificate is not signed by the active mkcert CA. Regenerate it."
  openssl x509 -in "$cert" -noout -checkend 86400 >/dev/null ||
    fail "Development certificate is expired or expires within 24 hours. Regenerate it."

  local sans
  sans=$(openssl x509 -in "$cert" -noout -ext subjectAltName)
  local required_name
  for required_name in localhost traefik.localhost '*.hyac.localhost'; do
    grep -Fq "DNS:$required_name" <<<"$sans" ||
      fail "Certificate SAN does not include $required_name. Regenerate it from the documented mkcert command."
  done

  local cert_key_hash private_key_hash
  cert_key_hash=$(openssl x509 -in "$cert" -pubkey -noout | openssl sha256)
  private_key_hash=$(openssl pkey -in "$key" -pubout | openssl sha256)
  [[ "$cert_key_hash" == "$private_key_hash" ]] || fail "Development certificate and key do not match."
}

preflight() {
  [[ -f "$ENV_FILE" ]] || fail "Missing $ENV_FILE. Copy .env.example and configure development-only values."
  [[ "$WAIT_TIMEOUT" =~ ^[1-9][0-9]*$ ]] || fail "HYAC_WAIT_TIMEOUT must be a positive integer."

  for command in docker openssl mkcert curl awk grep; do
    require_command "$command"
  done
  docker compose version >/dev/null
  docker info >/dev/null 2>&1 || fail "Docker daemon is not available to the current user."
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet

  local domain app_path expected_app_path
  domain=$(resolved_environment_value DOMAIN_NAME)
  [[ "$domain" == "hyac.localhost" ]] || fail "DOMAIN_NAME must be hyac.localhost for local development."

  app_path=$(resolved_environment_value APP_CODE_PATH_ON_HOST)
  expected_app_path=$(realpath "$REPO_ROOT/app")
  [[ "$app_path" == "$expected_app_path" ]] ||
    fail "APP_CODE_PATH_ON_HOST must be the canonical path $expected_app_path."

  verify_certificate
  printf 'Development preflight passed.\n'
}

verify_endpoints() {
  local url deadline
  for url in \
    https://console.hyac.localhost/ \
    https://server.hyac.localhost/docs \
    https://traefik.localhost/api/overview \
    http://127.0.0.1:9002/health; do
    deadline=$((SECONDS + WAIT_TIMEOUT))
    until curl --noproxy '*' --fail --silent --output /dev/null "$url"; do
      ((SECONDS < deadline)) || fail "Development endpoint did not become ready: $url"
      sleep 1
    done
  done
  printf 'Development endpoints are healthy.\n'
}

case ${1:-} in
  "") ;;
  --check) CHECK_ONLY=true ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; fail "Unknown argument: $1" ;;
esac

cd "$REPO_ROOT"
preflight
if [[ "$CHECK_ONLY" == true ]]; then
  exit 0
fi

COMPOSE=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
"${COMPOSE[@]}" build server web app lsp-sidecar
"${COMPOSE[@]}" up -d --wait --wait-timeout "$WAIT_TIMEOUT" \
  mongodb rustfs traefik server lsp-sidecar web
verify_endpoints
"${COMPOSE[@]}" ps
