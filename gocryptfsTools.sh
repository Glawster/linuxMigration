#!/usr/bin/env bash

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source logUtils.sh from organiseMyProjects (adjust path if needed)
_LOG_UTILS="$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))' 2>/dev/null)/logUtils.sh"
if [[ -f "$_LOG_UTILS" ]]; then
  source "$_LOG_UTILS"
else
  # Fallback: basic log function if organiseMyProjects not installed
  logFile="/dev/null"
  log_init()  { logFile="${HOME}/.local/state/${1}/${1}-$(date +%Y-%m-%d).log"; mkdir -p "$(dirname "$logFile")"; }
  log_info()  { echo "...$1"; }
  log_doing() { echo "$1..."; }
  log_done()  { echo "...$1"; }
  log_warn()  { echo "WARNING: $1" >&2; }
  log_error() { echo "ERROR: $1" >&2; }
  log_value() { echo "...$1: $2"; }
  log_action(){ echo "...$1"; }
  log_box()   { echo "=== $1 ==="; }
fi

log_init "gocryptfsTools"

# ===== config =====
ENCRYPTED_DIR="/mnt/myVideo/encrypted"
DECRYPTED_DIR="/mnt/myVideo/decrypted"

# ===== helpers =====
isMounted() {
    mountpoint -q "$DECRYPTED_DIR"
}

# ===== mount =====
mountGocryptfs() {
    if isMounted; then
        log_info "already mounted: $DECRYPTED_DIR"
        return 0
    fi

    log_doing "mounting gocryptfs"
    log_value "encrypted dir" "$ENCRYPTED_DIR"
    log_value "decrypted dir" "$DECRYPTED_DIR"

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        return 0
    fi

    mkdir -p "$DECRYPTED_DIR"

    gocryptfs "$ENCRYPTED_DIR" "$DECRYPTED_DIR"

    log_done "mount complete"
}

# ===== unmount =====
umountGocryptfs() {
    if ! isMounted; then
        log_info "not mounted: $DECRYPTED_DIR"
        return 0
    fi

    log_doing "unmounting gocryptfs"

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        return 0
    fi

    if fusermount -u "$DECRYPTED_DIR"; then
        log_done "unmounted cleanly"
        return 0
    fi

    log_warn "normal unmount failed, attempting lazy unmount"

    fusermount -uz "$DECRYPTED_DIR"

    log_done "lazy unmount complete"
}

# ===== status =====
statusGocryptfs() {
    if isMounted; then
        log_info "mounted: $DECRYPTED_DIR"
    else
        log_info "not mounted: $DECRYPTED_DIR"
    fi
}

# ===== CLI =====
case "${1:-}" in
    mount)
        mountGocryptfs
        ;;
    umount|unmount)
        umountGocryptfs
        ;;
    status)
        statusGocryptfs
        ;;
    *)
        echo "usage: $0 {mount|umount|status}"
        exit 1
        ;;
esac