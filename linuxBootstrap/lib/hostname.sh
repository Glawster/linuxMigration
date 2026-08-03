#!/usr/bin/env bash

hostnameApply() {
    local desired="${1:-}"
    [[ -n "$desired" ]] || return 0
    [[ "$desired" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]{0,62}$ ]] || { logError "invalid hostname: $desired"; return 2; }
    if [[ "$(hostnamectl --static 2>/dev/null || hostname)" == "$desired" ]]; then
        itemSkip "hostname already configured: $desired"
    else
        changeRun "set hostname to $desired" sudo hostnamectl set-hostname "$desired"
    fi
}
