#!/usr/bin/env bash
set -euo pipefail

vendor_id="0x04c5"
product_id="0x128d"
scanner_label="ScanSnap S1300i"

log() {
    printf '...%s\n' "$*"
}

error() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
usage:
  scansnapToVM <domain-name>
  SCANSNAP_VM="<domain-name>" scansnapToVM

what it does:
  - checks the ScanSnap is visible on the host
  - attaches it to a running libvirt guest using virsh attach-device
  - uses live attach by default
  - optionally also persists it with --config if SCANSNAP_PERSIST=1

examples:
  scansnapToVM win11
  SCANSNAP_VM=win11 scansnapToVM
  SCANSNAP_VM=win11 SCANSNAP_PERSIST=1 scansnapToVM
EOF
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || error "missing command: $1"
}

resolve_vm_name() {
    local vm_name="${1:-${SCANSNAP_VM:-}}"

    if [[ -n "$vm_name" ]]; then
        printf '%s\n' "$vm_name"
        return 0
    fi

    local running_count
    running_count="$(virsh list --name | sed '/^$/d' | wc -l | tr -d ' ')"

    if [[ "$running_count" == "1" ]]; then
        virsh list --name | sed '/^$/d' | head -1
        return 0
    fi

    error "no vm name supplied and unable to infer one. pass a domain name or set SCANSNAP_VM."
}

assert_vm_running() {
    local vm_name="$1"
    virsh list --name | sed '/^$/d' | grep -Fx "$vm_name" >/dev/null 2>&1 \
        || error "vm is not running: $vm_name"
}

show_host_scanner() {
    lsusb | awk '
        BEGIN { IGNORECASE = 1 }
        /04c5:128d/ { print; found=1 }
        END { if (!found) exit 1 }
    '
}

build_usb_xml() {
    cat <<EOF
<hostdev mode='subsystem' type='usb' managed='yes'>
  <source>
    <vendor id='${vendor_id}'/>
    <product id='${product_id}'/>
  </source>
</hostdev>
EOF
}

already_attached() {
    local vm_name="$1"
    virsh dumpxml "$vm_name" | grep -qi "<vendor id='${vendor_id}'/>" &&
    virsh dumpxml "$vm_name" | grep -qi "<product id='${product_id}'/>"
}

main() {
    require_command virsh
    require_command lsusb
    require_command mktemp

    if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
        usage
        exit 0
    fi

    local vm_name
    vm_name="$(resolve_vm_name "${1:-}")"

    log "target vm: $vm_name"
    assert_vm_running "$vm_name"

    log "checking host for ${scanner_label}..."
    local host_line
    host_line="$(show_host_scanner)" || error "scanner not visible on host usb bus"
    log "host scanner: $host_line"

    if already_attached "$vm_name"; then
        log "scanner already appears attached in domain xml: $vm_name"
        exit 0
    fi

    local tmp_xml
    tmp_xml="$(mktemp --suffix=.xml)"
    trap 'rm -f "$tmp_xml"' EXIT

    build_usb_xml > "$tmp_xml"

    log "attaching scanner to running vm..."
    virsh attach-device "$vm_name" "$tmp_xml" --live

    if [[ "${SCANSNAP_PERSIST:-0}" == "1" ]]; then
        log "also saving attachment to vm config..."
        virsh attach-device "$vm_name" "$tmp_xml" --config
    fi

    log "scanner attached to vm: $vm_name"
    if [[ "${SCANSNAP_PERSIST:-0}" == "1" ]]; then
        log "attachment is persistent across reboots"
    else
        log "attachment is live only; restart the vm and you may need to reattach"
    fi
}

main "$@"