#!/usr/bin/env bash
# lib/run.sh
#
# Two execution styles:
#   - runCmd <argv...>  : argument-safe command execution
#   - runSh  "<script>" : shell snippet execution (pipes/redirs/cd/&& etc.)
#

DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="${DRY_PREFIX:-[]}"

isLocalMode() {
  [[ "${LOCAL_MODE:-0}" == "1" ]] || [[ "${SSH_TARGET:-}" == "local" ]]
}

dryrun() {
  echo "${DRY_PREFIX:-...[]} $*"
}

ensureSshOpts() {
  if [[ -n "${SSH_TARGET:-}" ]]; then
    if ! declare -p SSH_OPTS >/dev/null 2>&1; then
      buildSshOpts
    fi
  fi
}

# run a command with args like python --version
runCmd() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$@"
    return 0
  fi

  if isLocalMode; then
    "$@"
  else
    ensureSshOpts
    local cmd=""
    printf -v cmd "%q " "$@"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -lc $(printf '%q' "$cmd")"
  fi
}

# run a command with args and capture output
runCmdCapture() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "(dry-run capture)"
    return 0
  fi

  if isLocalMode; then
    "$@" 2>&1
  else
    ensureSshOpts
    local cmd=""
    printf -v cmd "%q " "$@"
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -lc $(printf '%q' "$cmd")" 2>&1
  fi
}

# run a shell script snippet
runSh() {
  local script="${1:-}"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$script"
    return 0
  fi

  if isLocalMode; then
    bash -lc "$script"
  else
    ensureSshOpts
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -lc $(printf '%q' "$script")"
  fi
}

# run a shell script snippet and capture output
runShCapture() {
  local script="${1:-}"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "(dry-run capture)"
    return 0
  fi

  if isLocalMode; then
    bash -lc "$script" 2>&1
  else
    ensureSshOpts
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -lc $(printf '%q' "$script")" 2>&1
  fi
}

runHostCmd() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$@"
    return 0
  fi
  "$@"
}
