#!/usr/bin/env bash

set -euo pipefail

# ===== config =====
ENCRYPTED_DIR="/mnt/myVideo/encrypted"
DECRYPTED_DIR="/mnt/myVideo/decrypted"

# ===== logging =====
prefix="..."
[[ "${DRY_RUN:-0}" == "1" ]] && prefix="...[] "

log() {
    echo "${prefix}$1"
}

# ===== helpers =====
isMounted() {
    mountpoint -q "$DECRYPTED_DIR"
}

# ===== mount =====
mountGocryptfs() {
    if isMounted; then
        log "already mounted: $DECRYPTED_DIR"
        return 0
    fi

    log "mounting gocryptfs..."
    log "encrypted dir: $ENCRYPTED_DIR"
    log "decrypted dir: $DECRYPTED_DIR"

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        return 0
    fi

    mkdir -p "$DECRYPTED_DIR"

    gocryptfs "$ENCRYPTED_DIR" "$DECRYPTED_DIR"

    log "mount complete..."
}

# ===== unmount =====
umountGocryptfs() {
    if ! isMounted; then
        log "not mounted: $DECRYPTED_DIR"
        return 0
    fi

    log "unmounting gocryptfs..."

    if [[ "${DRY_RUN:-0}" == "1" ]]; then
        return 0
    fi

    if fusermount -u "$DECRYPTED_DIR"; then
        log "unmounted cleanly..."
        return 0
    fi

    log "normal unmount failed, attempting lazy unmount..."

    fusermount -uz "$DECRYPTED_DIR"

    log "lazy unmount complete..."
}

# ===== status =====
statusGocryptfs() {
    if isMounted; then
        log "mounted: $DECRYPTED_DIR"
    else
        log "not mounted: $DECRYPTED_DIR"
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