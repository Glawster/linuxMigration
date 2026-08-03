#!/usr/bin/env bash

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
