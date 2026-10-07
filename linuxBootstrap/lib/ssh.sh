#!/usr/bin/env bash

sshApply() {
    local sshDir="$HOME/.ssh" configFile="$HOME/.ssh/config" includeLine='Include config.d/*.conf'
    if [[ -d "$sshDir" && "$(stat -c '%a' "$sshDir")" == 700 ]]; then
        itemSkip "SSH directory already configured"
    elif [[ -d "$sshDir" ]]; then
        changeRun "set SSH directory permissions" chmod 700 "$sshDir"
    else
        changeRun "create SSH directory" mkdir -m 700 -p "$sshDir"
    fi

    if [[ -f "$configFile" ]] && grep -Fxq "$includeLine" "$configFile"; then
        itemSkip "SSH config includes managed snippets"
    else
        changeRun "enable managed SSH config snippets" _sshConfigIncludeInstall "$configFile" "$includeLine"
    fi
}

_sshConfigIncludeInstall() {
    local configFile="$1" includeLine="$2"
    mkdir -p "$(dirname "$configFile")/config.d"
    if [[ -f "$configFile" ]]; then
        printf '\n%s\n' "$includeLine" >> "$configFile"
    else
        printf '%s\n' "$includeLine" > "$configFile"
    fi
    chmod 600 "$configFile"
}
