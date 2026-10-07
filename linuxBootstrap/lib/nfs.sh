#!/usr/bin/env bash

nfsExportsApply() {
    (($#)) || return 0
    local entry path client target="${nfsExportsFile:-/etc/exports.d/linux-bootstrap.exports}" temporary
    for entry in "$@"; do
        read -r path client _ <<< "$entry"
        [[ "$path" == /* && -n "$client" ]] || { logError "invalid NFS export entry: $entry"; return 2; }
    done
    if ! command -v exportfs >/dev/null && (( ! ${dryRun:-1} )); then commandRequire exportfs; fi

    temporary="$(mktemp)"
    printf '%s\n' "$@" > "$temporary"
    if [[ -f "$target" ]] && cmp -s "$target" "$temporary"; then
        itemSkip "NFS exports already configured"
    else
        changeRun "configure NFS exports" _nfsExportsInstall "$temporary" "$target"
    fi
    rm -f "$temporary"
}

nfsMountsApply() {
    (($#)) || return 0
    local entry source target options fstab="${nfsFstabFile:-/etc/fstab}" temporary
    for entry in "$@"; do
        read -r source target options _ <<< "$entry"
        [[ "$source" == *:* && "$target" == /* ]] || { logError "invalid NFS mount entry: $entry"; return 2; }
    done

    temporary="$(mktemp)"
    _nfsMountsFileRender "$fstab" "$temporary" "$@"
    if cmp -s "$fstab" "$temporary"; then
        itemSkip "NFS mount definitions already configured"
    else
        changeRun "configure NFS mount definitions" sudo install -m 644 "$temporary" "$fstab"
    fi
    rm -f "$temporary"

    for entry in "$@"; do
        read -r source target options _ <<< "$entry"
        if findmnt --mountpoint "$target" --source "$source" >/dev/null 2>&1; then
            itemSkip "NFS mount active: $target"
        else
            changeRun "mount NFS share: $target" _nfsMountActivate "$target"
        fi
    done
}

_nfsExportsInstall() {
    local source="$1" target="$2"
    sudo install -D -m 644 "$source" "$target"
    sudo exportfs -ra
}

_nfsMountActivate() {
    local target="$1"
    sudo mkdir -p "$target"
    sudo mount "$target"
}

_nfsMountsFileRender() {
    local source="$1" output="$2" entry remote target options
    shift 2
    awk '
        $0 == "# BEGIN linux-bootstrap NFS mounts" { managed=1; next }
        $0 == "# END linux-bootstrap NFS mounts" { managed=0; next }
        !managed { print }
    ' "$source" > "$output"
    printf '# BEGIN linux-bootstrap NFS mounts\n' >> "$output"
    for entry in "$@"; do
        read -r remote target options _ <<< "$entry"
        options="${options:-defaults,_netdev,nofail,x-systemd.automount}"
        printf '%s %s nfs4 %s 0 0\n' "$remote" "$target" "$options" >> "$output"
    done
    printf '# END linux-bootstrap NFS mounts\n' >> "$output"
}
