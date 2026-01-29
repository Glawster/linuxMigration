#!/usr/bin/env bash
# lib/common.sh
#
# common helpers used by steps
# IMPORTANT: steps should only call `runCmd` and `runSh` from here

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
    runCmd mkdir -p "$dir"
  fi
}

ensureRemoteConfigured() {
  if [[ "${REQUIRE_REMOTE}" == "1" ]]; then
    if [[ -z "${SSH_TARGET:-}" ]]; then
      die "Remote execution required but SSH_TARGET is not set."
    fi
    if ! declare -F runCmd >/dev/null 2>&1; then
      die "Remote execution required but runCmd() is not available (did you source lib/run.sh?)."
    fi
  fi
}
