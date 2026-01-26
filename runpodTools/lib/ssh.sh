#!/usr/bin/env bash
set -euo pipefail

isCommandRemote() {
  # usage: isCommandRemote <ssh_target> <cmd>
  local target="${1:-}"
  local cmd="${2:-}"

  if [[ -z "${target}" || -z "${cmd}" ]]; then
    return 1
  fi

  # always (re)build opts; avoids array-length quirks
  buildSshOpts

  ssh "${SSH_OPTS[@]}" "$target" "command -v '$cmd' >/dev/null 2>&1"
}

# ssh.sh

runRemote() {
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
}

runRemoteCapture() {
  local cmd="$1"
  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -lc $(printf '%q' "$cmd")"
}

buildSshOpts() {
  declare -ag SSH_OPTS
  declare -ag SCP_OPTS

  SSH_OPTS=()
  SCP_OPTS=()

  [[ -n "${SSH_PORT:-}" ]] && SSH_OPTS+=(-p "$SSH_PORT")
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)
  [[ -n "${SSH_IDENTITY:-}" ]] && SSH_OPTS+=(-i "$SSH_IDENTITY")
  
  [[ -n "${SSH_PORT:-}" ]] && SCP_OPTS+=(-P "$SSH_PORT")
  SCP_OPTS+=(-o StrictHostKeyChecking=accept-new)
  [[ -n "${SSH_IDENTITY:-}" ]] && SCP_OPTS+=(-i "$SSH_IDENTITY")
  return 0
}
