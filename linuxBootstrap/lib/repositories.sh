#!/usr/bin/env bash

repositoriesApply() {
    local repository
    for repository in "$@"; do
        case "$repository" in
            warp) repositoryWarpApply ;;
            *) logError "repository has no definition: $repository"; return 2 ;;
        esac
    done
}

repositoryWarpApply() {
    local architecture keyFile listFile definition
    architecture="$(dpkg --print-architecture)"
    [[ "$architecture" == amd64 || "$architecture" == arm64 ]] || {
        logError "unsupported Warp repository architecture: $architecture"
        return 2
    }
    keyFile="/etc/apt/keyrings/warpdotdev.gpg"
    listFile="/etc/apt/sources.list.d/warpdotdev.list"
    definition="deb [arch=$architecture signed-by=$keyFile] https://releases.warp.dev/linux/deb stable main"
    if [[ -f "$keyFile" && -f "$listFile" ]] && grep -Fxq "$definition" "$listFile"; then
        itemSkip "apt repository already configured: warp"
    else
        changeRun "configure apt repository: warp" repositoryWarpInstall "$keyFile" "$listFile" "$definition"
    fi
}

repositoryWarpInstall() {
    local keyFile="$1" listFile="$2" definition="$3" keySource keyBinary listSource
    keySource="$(mktemp)"
    keyBinary="$(mktemp)"
    listSource="$(mktemp)"
    curl -fsSL https://releases.warp.dev/linux/keys/warp.asc -o "$keySource"
    gpg --batch --yes --dearmor --output "$keyBinary" "$keySource"
    printf '%s\n' "$definition" > "$listSource"
    sudo install -D -o root -g root -m 644 "$keyBinary" "$keyFile"
    sudo install -D -o root -g root -m 644 "$listSource" "$listFile"
    rm -f "$keySource" "$keyBinary" "$listSource"
    sudo apt-get update
}
