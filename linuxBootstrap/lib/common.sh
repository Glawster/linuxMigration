#!/usr/bin/env bash

summaryChanged=0
summarySkipped=0
summaryFailed=0

argumentRequireValue() {
    local option="$1" value="$2"
    [[ -n "$value" && "$value" != --* ]] || { logError "$option requires a value"; exit 2; }
}

commandRequire() {
    command -v "$1" >/dev/null 2>&1 || { logError "required command not found: $1"; return 127; }
}

changeRun() {
    local description="$1"
    shift
    if [[ "${dryRun:-1}" == 1 ]]; then
        logInfo "would $description"
        ((summaryChanged += 1))
        return 0
    fi
    logInfo "$description"
    if "$@"; then
        logSuccess "$description"
        ((summaryChanged += 1))
    else
        ((summaryFailed += 1))
        return 1
    fi
}

itemSkip() {
    logVerbose "$1"
    ((summarySkipped += 1))
}

errorTrap() {
    local status="$1" line="$2" command="$3"
    logError "command failed at line $line (exit $status): $command"
}

servicesApply() {
    local service
    for service in "$@"; do
        if systemctl is-enabled --quiet "$service" 2>/dev/null; then
            itemSkip "service already enabled: $service"
        else
            changeRun "enable service: $service" sudo systemctl enable --now "$service"
        fi
    done
}

summaryPrint() {
    local profilesText="" profile
    for profile in "${loadedProfiles[@]}"; do
        [[ -z "$profilesText" ]] || profilesText+=", "
        profilesText+="$profile"
    done
    printf '\nSummary\n'
    printf '  Command ......... %s\n' "${requestedCommand:-install}"
    printf '  Profiles ........ %s\n' "$profilesText"
    [[ -z "${profileMasterName:-}" ]] || printf '  Config master ... %s (%s)\n' "$profileMasterName" "$profileMasterHostname"
    [[ -z "${profileExpectedIp:-}" ]] || printf '  Expected IP ..... %s (DHCP reservation)\n' "$profileExpectedIp"
    printf '  Mode ............ %s\n' "$([[ "${dryRun:-1}" == 1 ]] && echo dry-run || echo apply)"
    printf '  Changes ......... %d\n' "$summaryChanged"
    printf '  Already OK ...... %d\n' "$summarySkipped"
    printf '  Failures ........ %d\n' "$summaryFailed"
    ((summaryFailed == 0)) || return 1
    logSuccess "bootstrap complete"
}
