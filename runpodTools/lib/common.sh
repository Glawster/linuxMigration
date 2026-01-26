#!/usr/bin/env bash
# lib/common.sh
#
# common helpers used by steps
# IMPORTANT: steps should only call `run` and `isCommand`

set -euo pipefail

# expected env:
#   DRY_RUN (0/1)
#   DRY_PREFIX (e.g. "[]")
#   REQUIRE_REMOTE (0/1)  <-- if 1, we refuse to run locally
#   SSH_TARGET, SSH_PORT, SSH_IDENTITY (for remote)

source "$LIB_DIR/ssh.sh"
source "$LIB_DIR/run.sh"

DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="${DRY_PREFIX:-[]}"
REQUIRE_REMOTE="${REQUIRE_REMOTE:-0}"

# Logging functions
log() { # used to giva an update to a task being actioned
  echo -e "...$*"
}

logTask() { # used to say "am starting this task"
  echo -e "$*...\n"
}
warn() {
  echo -e "WARNING: $*\n" >&2
}

error() {
  echo -e "ERROR: $*\n" >&2
}

die() {
  echo -e "FATALITY: $*\n" >&2
  exit 1
}

# Ensure directory exists
ensureDir() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    run mkdir -p "$dir"
  fi
}

ensureRemoteConfigured() {
  if [[ "${REQUIRE_REMOTE}" == "1" ]]; then
    if [[ -z "${SSH_TARGET:-}" ]]; then
      die "Remote execution required but SSH_TARGET is not set."
    fi
    if ! declare -F runRemote >/dev/null 2>&1; then
      die "Remote execution required but runRemote() is not available (did you source lib/ssh.sh?)."
    fi
  fi
}

isCommand() {
  # usage: isCommand <cmd>
  ensureRemoteConfigured
  local cmd="$1"

  if [[ -n "${SSH_TARGET:-}" ]] && declare -F isCommandRemote >/dev/null 2>&1; then
    isCommandRemote "${SSH_TARGET}" "$cmd"
    return $?
  fi

  if [[ "${REQUIRE_REMOTE}" == "1" ]]; then
    die "Remote execution required but isCommandRemote not active."
  fi

  command -v "$cmd" >/dev/null 2>&1
}

hasCmd() {
  # usage: hasCmd <command>
  local cmd="$1"
  run bash -lc "
    command -v '${cmd}' >/dev/null 2>&1 || \
    test -x '/usr/bin/${cmd}' || \
    test -x '/bin/${cmd}' || \
    test -x '/usr/sbin/${cmd}' || \
    test -x '/sbin/${cmd}'
  "
}
