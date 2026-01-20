#!/usr/bin/env bash
# lib/ssh.sh
# SSH helpers for executing commands on remote

# Execute command on remote via SSH
# Uses exported SSH_TARGET, SSH_PORT, SSH_IDENTITY from main script
sshExec() {
  local cmd="$1"
  
  local ssh_opts=(-p "${SSH_PORT:-22}" -o StrictHostKeyChecking=accept-new)
  if [[ -n "${SSH_IDENTITY:-}" ]]; then
    ssh_opts+=(-i "$SSH_IDENTITY")
  fi
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "...[] would ssh: $cmd"
    return 0
  fi
  
  # shellcheck disable=SC2029
  ssh "${ssh_opts[@]}" "${SSH_TARGET}" "$cmd"
}

# Execute multi-line command on remote via heredoc
sshExecHeredoc() {
  local ssh_opts=(-p "${SSH_PORT:-22}" -o StrictHostKeyChecking=accept-new)
  if [[ -n "${SSH_IDENTITY:-}" ]]; then
    ssh_opts+=(-i "$SSH_IDENTITY")
  fi
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    log "...[] would ssh with heredoc"
    cat
    return 0
  fi
  
  ssh "${ssh_opts[@]}" "${SSH_TARGET}" 'bash -s'
}

# Check if command exists on remote
sshCommandExists() {
  local cmd="$1"
  sshExec "command -v $cmd" >/dev/null 2>&1
}

# Check if directory exists on remote
sshDirExists() {
  local dir="$1"
  sshExec "test -d '$dir'" >/dev/null 2>&1
}

# Check if file exists on remote
sshFileExists() {
  local file="$1"
  sshExec "test -f '$file'" >/dev/null 2>&1
}

# Check if git repo exists on remote
sshGitRepoExists() {
  local dir="$1"
  sshExec "test -d '$dir/.git'" >/dev/null 2>&1
}
