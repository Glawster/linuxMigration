#!/usr/bin/env bash
# ssh.sh

#runRemote() {
#  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$@"
#}

#runRemoteCapture() {
#  local cmd="$1"
#  ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "bash -lc $(printf '%q' "$cmd")"
#}

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
