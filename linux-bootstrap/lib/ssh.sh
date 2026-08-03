#!/usr/bin/env bash

sshApply() {
    local sshDir="$HOME/.ssh"
    if [[ -d "$sshDir" && "$(stat -c '%a' "$sshDir")" == 700 ]]; then
        itemSkip "SSH directory already configured"
    elif [[ -d "$sshDir" ]]; then
        changeRun "set SSH directory permissions" chmod 700 "$sshDir"
    else
        changeRun "create SSH directory" mkdir -m 700 -p "$sshDir"
    fi
}
