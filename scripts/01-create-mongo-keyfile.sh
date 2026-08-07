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

ensure_safe_keyfile_path() {
  if [[ -L "${KEYFILE}" ]]; then
    fail "${KEYFILE} must not be a symbolic link"
  fi
  if [[ -e "${KEYFILE}" && ! -f "${KEYFILE}" ]]; then
    fail "${KEYFILE} exists but is not a regular file"
  fi
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

repair_existing_keyfile() {
  ensure_safe_keyfile_path
  resolve_mongo_ids
  chmod 400 "${KEYFILE}"
  if [[ "$(id -u)" -eq 0 ]]; then
    chown "${MONGO_UID}:${MONGO_GID}" "${KEYFILE}"
    log "owner set to ${MONGO_UID}:${MONGO_GID}"
  else
    log "not running as root; cannot change keyfile ownership"
  fi

  local actual_mode actual_owner expected_owner
  actual_mode="$(stat -c "%a" "${KEYFILE}")"
  actual_owner="$(stat -c "%u:%g" "${KEYFILE}")"
  expected_owner="${MONGO_UID}:${MONGO_GID}"
  [[ "${actual_mode}" == "400" ]] || fail "keyfile mode is ${actual_mode}; expected 400"
  [[ "${actual_owner}" == "${expected_owner}" ]] || fail "keyfile owner is ${actual_owner}; expected ${expected_owner}. Run this script as root or provide matching MONGO_UID/MONGO_GID."
}

generate_keyfile() {
  local keyfile_dir keyfile_name temp_file
  keyfile_dir="$(dirname -- "${KEYFILE}")"
  keyfile_name="$(basename -- "${KEYFILE}")"
  [[ -d "${keyfile_dir}" ]] || fail "keyfile directory does not exist: ${keyfile_dir}"
  [[ ! -L "${keyfile_dir}" ]] || fail "keyfile directory must not be a symbolic link: ${keyfile_dir}"

  temp_file="$(mktemp "${keyfile_dir}/.${keyfile_name}.tmp.XXXXXX")"
  trap 'rm -f -- "${temp_file}"' EXIT
  openssl rand -base64 756 > "${temp_file}"
  chmod 600 "${temp_file}"

  # Re-check immediately before the atomic replacement. mv -T replaces a link
  # itself if one appears concurrently; it never follows the link target.
  ensure_safe_keyfile_path
  mv -fT -- "${temp_file}" "${KEYFILE}"
  trap - EXIT
}

main() {
  ensure_safe_keyfile_path

  if [[ -s "${KEYFILE}" && "${FORCE_REGEN}" != "1" ]]; then
    log "${KEYFILE} already exists and is non-empty"
    repair_existing_keyfile
    log "Set FORCE_REGEN=1 to regenerate"
    ls -l "${KEYFILE}"
    exit 0
  fi

  command -v openssl >/dev/null 2>&1 || fail "openssl not found"

  # umask 077 确保新文件默认就是严格权限
  umask 077
  generate_keyfile

  repair_existing_keyfile

  log "generated ${KEYFILE}"
  ls -l "${KEYFILE}"
}

main "$@"
