#!/usr/bin/env bash

logFile=""

if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    colourBlue=$'\033[34m'
    colourYellow=$'\033[33m'
    colourRed=$'\033[31m'
    colourGreen=$'\033[32m'
    colourReset=$'\033[0m'
else
    colourBlue="" colourYellow="" colourRed="" colourGreen="" colourReset=""
fi

logInfo() { printf '%sINFO%s     %s\n' "$colourBlue" "$colourReset" "$*"; }
logWarning() { printf '%sWARNING%s  %s\n' "$colourYellow" "$colourReset" "$*"; }
logError() { printf '%sERROR%s    %s\n' "$colourRed" "$colourReset" "$*" >&2; }
logSuccess() { printf '%sSUCCESS%s  %s\n' "$colourGreen" "$colourReset" "$*"; }
logVerbose() { [[ "${verbose:-0}" == 1 ]] && logInfo "$*" || true; }

loggingInitialize() {
    local stateRoot logDir timestamp
    stateRoot="${XDG_STATE_HOME:-${HOME:?HOME is required}/.local/state}"
    logDir="$stateRoot/linuxBootstrap"
    timestamp="$(date '+%Y%m%d-%H%M%S')"
    if ! mkdir -p "$logDir"; then
        logWarning "could not create log directory: $logDir"
        return 0
    fi
    chmod 700 "$logDir" 2>/dev/null || true
    logFile="$logDir/bootstrap-$timestamp-$$.log"
    if ! touch "$logFile"; then
        logWarning "could not create log file: $logFile"
        logFile=""
        return 0
    fi
    chmod 600 "$logFile" 2>/dev/null || true
    exec > >(tee -a "$logFile") 2>&1
    logInfo "log file: $logFile"
}
