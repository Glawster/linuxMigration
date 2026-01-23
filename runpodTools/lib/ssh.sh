#!/usr/bin/env bash
set -euo pipefail

isCommandRemote() {
  # Returns 0 (true) if a command is clearly intended to run remotely.
  # We treat "ssh ..." as remote and also anything executed via runRemote().
  #
  # usage: isCommandRemote "$@"

  [[ $# -ge 1 ]] || return 1

  case "$1" in
    ssh)
      return 0
      ;;
  esac

  return 1
}

# Build SSH options as an ARRAY (never a string)
buildSshOpts() {
  SSH_OPTS=()

  if [[ -n "${SSH_PORT:-}" ]]; then
    SSH_OPTS+=(-p "$SSH_PORT")
  fi

  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)

  if [[ -n "${SSH_IDENTITY:-}" ]]; then
    SSH_OPTS+=(-i "$SSH_IDENTITY")
  fi
}

runRemote() {
  if [[ -z "${SSH_TARGET:-}" ]]; then
    echo "ERROR: SSH_TARGET is not set" >&2
    return 1
  fi

  buildSshOpts

  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-[]} ssh ${SSH_OPTS[*]} ${SSH_TARGET} $*"
    return 0
  fi

  # Build ONE remote command string (argv-safe)
  local remoteCmd=""
  printf -v remoteCmd "%q " "$@"

  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$remoteCmd"
}
