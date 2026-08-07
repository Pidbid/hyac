#!/usr/bin/env bash
set -euo pipefail

: "${CI_SMOKE_IMAGE_TAG:?set CI_SMOKE_IMAGE_TAG to the pushed release tag}"

compose_file=".github/compose-smoke.yml"
project_name="hyac-release-smoke"
dynamic_dir="$(mktemp -d)"
export CI_SMOKE_DYNAMIC_DIR="${dynamic_dir}"
export CI_SMOKE_MONGO_USERNAME="hyac-ci-root"
export CI_SMOKE_MONGO_PASSWORD="ci-mongo-password-only-for-disposable-smoke"
export CI_SMOKE_S3_ACCESS_KEY="ci-smoke-access-key"
export CI_SMOKE_S3_SECRET_KEY="ci-smoke-secret-key-only-for-disposable-run"
export CI_SMOKE_ADMIN_PASSWORD="Ci-Smoke-Admin-Password-2026!"

cleanup() {
  docker compose -p "${project_name}" -f "${compose_file}" down --volumes --remove-orphans || true
  rm -rf -- "${dynamic_dir}"
}
trap cleanup EXIT

openssl req -x509 -newkey rsa:2048 -nodes -days 1 \
  -keyout "${dynamic_dir}/ci.key" \
  -out "${dynamic_dir}/ci.crt" \
  -subj "/CN=*.ci.example.com" \
  -addext "subjectAltName=DNS:*.ci.example.com,DNS:ci.example.com" \
  >/dev/null 2>&1

cat > "${dynamic_dir}/tls.yml" <<EOF
tls:
  certificates:
    - certFile: /etc/traefik/dynamic/ci.crt
      keyFile: /etc/traefik/dynamic/ci.key
EOF

docker compose -p "${project_name}" -f "${compose_file}" pull
docker compose -p "${project_name}" -f "${compose_file}" up -d --wait --wait-timeout 240

captcha="ci42"
docker compose -p "${project_name}" -f "${compose_file}" exec -T mongodb \
  mongosh --quiet \
  -u "${CI_SMOKE_MONGO_USERNAME}" \
  -p "${CI_SMOKE_MONGO_PASSWORD}" \
  --authenticationDatabase admin \
  hyac \
  --eval "db.captchas.insertOne({text: '${captcha}', created_at: new Date(), expires_at: new Date(Date.now() + 300000), is_used: false})"

SMOKE_BASE_URL="https://console.ci.example.com:18443" \
SMOKE_ADMIN_USERNAME="operator" \
SMOKE_ADMIN_PASSWORD="${CI_SMOKE_ADMIN_PASSWORD}" \
SMOKE_CAPTCHA="${captcha}" \
node web/tests/production-smoke-function-lifecycle.mjs
