#!/usr/bin/env bash
# lib/ssh.sh
#
# minimal ssh transport helpers (no business logic)

set -euo pipefail

buildSshOpts() {
  # expects:
  #   SSH_PORT (optional)
  #   SSH_IDENTITY (optional)
  #
  # emits:
  #   SSH_OPTS (array)

  SSH_OPTS=()
  if [[ -n "${SSH_PORT:-}" ]]; then
    SSH_OPTS+=(-p "$SSH_PORT")
  fi

  # keep your existing behaviour
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)

  if [[ -n "${SSH_IDENTITY:-}" ]]; then
    SSH_OPTS+=(-i "$SSH_IDENTITY")
  fi
}

sshCmd() {
  # usage: sshCmd user@host <command...>
  local target="$1"
  shift
  ssh "${SSH_OPTS[@]}" "$target" "$@"
}

runRemote() {
  # usage: runRemote user@host <command...>
  local target="$1"
  shift
  sshCmd "$target" "$@"
}

isCommandRemote() {
  # usage: isCommandRemote user@host <cmd>
  local target="$1"
  local cmd="$2"
  sshCmd "$target" "command -v '$cmd' >/dev/null 2>&1"
}
