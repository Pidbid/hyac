#!/usr/bin/env bash
set -Eeuo pipefail

KEYFILE="${KEYFILE:-mongo-keyfile}"
FORCE_REGEN="${FORCE_REGEN:-0}"
MONGO_IMAGE="${MONGO_IMAGE:-mongo:8.0}"
MONGO_UID="${MONGO_UID:-}"
MONGO_GID="${MONGO_GID:-}"

log() {
  echo "[mongo-keyfile] $*"
}

fail() {
  echo "[mongo-keyfile] ERROR: $*" >&2
  exit 1
}

resolve_mongo_ids() {
  # 已显式传入则直接使用
  if [[ -n "${MONGO_UID}" && -n "${MONGO_GID}" ]]; then
    return 0
  fi

  # 尝试从镜像中读取 mongodb 用户 uid/gid
  if command -v docker >/dev/null 2>&1; then
    local out uid gid
    if out="$(docker run --rm --entrypoint bash "${MONGO_IMAGE}" -lc 'id -u mongodb 2>/dev/null && id -g mongodb 2>/dev/null' 2>/dev/null)"; then
      uid="$(echo "${out}" | sed -n '1p')"
      gid="$(echo "${out}" | sed -n '2p')"
      if [[ "${uid}" =~ ^[0-9]+$ && "${gid}" =~ ^[0-9]+$ ]]; then
        MONGO_UID="${uid}"
        MONGO_GID="${gid}"
        return 0
      fi
    fi
  fi

  # 回退默认值
  MONGO_UID="999"
  MONGO_GID="999"
}

main() {
  if [[ -e "${KEYFILE}" && ! -f "${KEYFILE}" ]]; then
    fail "${KEYFILE} exists but is not a regular file"
  fi

  if [[ -s "${KEYFILE}" && "${FORCE_REGEN}" != "1" ]]; then
    log "${KEYFILE} already exists and is non-empty"
    log "Set FORCE_REGEN=1 to regenerate"
    ls -l "${KEYFILE}"
    exit 0
  fi

  command -v openssl >/dev/null 2>&1 || fail "openssl not found"

  resolve_mongo_ids

  # umask 077 确保新文件默认就是严格权限
  umask 077
  openssl rand -base64 756 > "${KEYFILE}"

  # Mongo keyFile 权限必须严格
  chmod 400 "${KEYFILE}"

  if [[ "$(id -u)" -eq 0 ]]; then
    chown "${MONGO_UID}:${MONGO_GID}" "${KEYFILE}"
    log "owner set to ${MONGO_UID}:${MONGO_GID}"
  else
    log "not running as root, skip chown"
    log "if container cannot read keyfile, run:"
    log "  sudo chown ${MONGO_UID}:${MONGO_GID} ${KEYFILE}"
  fi

  log "generated ${KEYFILE}"
  ls -l "${KEYFILE}"
}

main "$@"
