#!/usr/bin/env bash

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source logUtils.sh from organiseMyProjects (adjust path if needed)
_LOG_UTILS="$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))' 2>/dev/null)/logUtils.sh"
if [[ -f "$_LOG_UTILS" ]]; then
  source "$_LOG_UTILS"
else
  # Fallback logging
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

B2_REMOTE="b2:Andy-weeNAS/encrypted"
B2_ENCRYPTED_DIR="${HOME}/mnt/b2-encrypted"
B2_DECRYPTED_DIR="${HOME}/mnt/b2-decrypted"
B2_DIR_CACHE_TIME="10m"
B2_VFS_CACHE_MODE="full"

# ===== helpers =====
isMounted() { mountpoint -q "$1"; }

# ===== help =====
showHelp() {
cat <<EOF

=== gocryptfsTools ===

A helper tool for managing local and Backblaze B2 gocryptfs mounts.

USAGE:
  $0 <command>

COMMANDS:
  mount              Mount local encrypted directory
  umount             Unmount local decrypted directory
  status             Show local mount status

  mount-b2           Mount B2 encrypted bucket (rclone)
  umount-b2          Unmount B2 encrypted mount
  status-b2          Show B2 encrypted mount status

  mount-b2-dec       Mount decrypted B2 backup (stacked mount)
  umount-b2-dec      Unmount decrypted B2 mount
  status-b2-dec      Show decrypted B2 mount status

  mount-backup       Mount B2 encrypted + decrypted (full stack)
  umount-backup      Unmount decrypted + encrypted B2 mounts
  status-backup      Show full backup mount status

CONFIG (defaults):
  ENCRYPTED_DIR=$ENCRYPTED_DIR
  DECRYPTED_DIR=$DECRYPTED_DIR

  B2_REMOTE=$B2_REMOTE
  B2_ENCRYPTED_DIR=$B2_ENCRYPTED_DIR
  B2_DECRYPTED_DIR=$B2_DECRYPTED_DIR

OVERRIDES:
  You can override any config via environment variables:

    B2_REMOTE='b2:mybucket/path' $0 mount-backup

WORKFLOW:

  Local:
    $0 mount
    # work with decrypted files
    $0 umount

  Backup test (no download):
    $0 mount-backup
    ls ~/mnt/b2-decrypted
    $0 umount-backup

NOTES:
  - B2 mounts use rclone FUSE
  - gocryptfs runs on top for decryption
  - Only accessed files are downloaded (on-demand)
  - Uses read-only mounts for safety

EOF
}

# ===== local mount =====
mountGocryptfs() {
    if isMounted "$DECRYPTED_DIR"; then
        log_info "already mounted: $DECRYPTED_DIR"
        return 0
    fi

    log_doing "mounting gocryptfs"
    log_value "encrypted dir" "$ENCRYPTED_DIR"
    log_value "decrypted dir" "$DECRYPTED_DIR"

    mkdir -p "$DECRYPTED_DIR"
    gocryptfs "$ENCRYPTED_DIR" "$DECRYPTED_DIR"
    log_done "mount complete"
}

umountGocryptfs() {
    if ! isMounted "$DECRYPTED_DIR"; then
        log_info "not mounted: $DECRYPTED_DIR"
        return 0
    fi

    log_doing "unmounting gocryptfs"
    fusermount -u "$DECRYPTED_DIR" || fusermount -uz "$DECRYPTED_DIR"
    log_done "unmounted"
}

statusGocryptfs() {
    isMounted "$DECRYPTED_DIR" && log_info "mounted" || log_info "not mounted"
}

# ===== B2 mount =====
mountB2() {
    if isMounted "$B2_ENCRYPTED_DIR"; then
        log_info "B2 already mounted"
        return 0
    fi

    mkdir -p "$B2_ENCRYPTED_DIR"

    log_doing "mounting B2 (rclone)"
    rclone mount "$B2_REMOTE" "$B2_ENCRYPTED_DIR" \
      --read-only \
      --dir-cache-time "$B2_DIR_CACHE_TIME" \
      --vfs-cache-mode "$B2_VFS_CACHE_MODE" &

    sleep 2
    log_done "B2 mount started"
}

umountB2() {
    fusermount -u "$B2_ENCRYPTED_DIR" 2>/dev/null || fusermount -uz "$B2_ENCRYPTED_DIR" || true
    log_done "B2 unmounted"
}

statusB2() {
    isMounted "$B2_ENCRYPTED_DIR" && log_info "mounted" || log_info "not mounted"
}

# ===== B2 decrypted =====
mountB2Dec() {
    mountB2

    if isMounted "$B2_DECRYPTED_DIR"; then
        log_info "B2 decrypted already mounted"
        return 0
    fi

    mkdir -p "$B2_DECRYPTED_DIR"
    log_doing "mounting gocryptfs (B2)"
    gocryptfs -ro "$B2_ENCRYPTED_DIR" "$B2_DECRYPTED_DIR"
    log_done "B2 decrypted mount ready"
}

umountB2Dec() {
    fusermount -u "$B2_DECRYPTED_DIR" 2>/dev/null || fusermount -uz "$B2_DECRYPTED_DIR" || true
    log_done "B2 decrypted unmounted"
}

statusB2Dec() {
    isMounted "$B2_DECRYPTED_DIR" && log_info "mounted" || log_info "not mounted"
}

# ===== combined =====
mountBackup() {
    mountB2Dec
}

umountBackup() {
    umountB2Dec
    umountB2
}

statusBackup() {
    statusB2
    statusB2Dec
}

# ===== CLI =====
case "${1:-}" in
    mount) mountGocryptfs ;;
    umount|unmount) umountGocryptfs ;;
    status) statusGocryptfs ;;

    mount-b2) mountB2 ;;
    umount-b2) umountB2 ;;
    status-b2) statusB2 ;;

    mount-b2-dec) mountB2Dec ;;
    umount-b2-dec) umountB2Dec ;;
    status-b2-dec) statusB2Dec ;;

    mount-backup) mountBackup ;;
    umount-backup) umountBackup ;;
    status-backup) statusBackup ;;

    help|-h|--help|"") showHelp ;;

    *)
        log_error "unknown command: $1"
        showHelp
        exit 1
        ;;
esac
