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

buildSshOpts() {
  declare -ag SSH_OPTS
  SSH_OPTS=()

  [[ -n "${SSH_PORT:-}" ]] && SSH_OPTS+=(-p "$SSH_PORT")
  SSH_OPTS+=(-o StrictHostKeyChecking=accept-new)
  [[ -n "${SSH_IDENTITY:-}" ]] && SSH_OPTS+=(-i "$SSH_IDENTITY")
  
  return 0
}
