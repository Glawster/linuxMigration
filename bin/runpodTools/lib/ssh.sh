#!/usr/bin/env bash
# lib/ssh.sh
# SSH command helpers for remote operations

# Build SSH command array safely
buildSshOpts() {
  local port="${SSH_PORT:-22}"
  local identity="${SSH_IDENTITY:-}"
  
  SSH_OPTS=(-p "$port" -o StrictHostKeyChecking=accept-new)
  
  if [[ -n "$identity" ]]; then
    SSH_OPTS+=(-i "$identity")
  fi
}

# Run command on remote host
runRemote() {
  local target="$1"
  shift
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} ssh ${SSH_OPTS[*]} ${target} $*"
    return 0
  fi
  
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "$target" "$@"
}

# Copy file to remote using rsync with fallback to scp
copyToRemote() {
  local src="$1"
  local target="$2"
  local dst="$3"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} rsync/scp $src -> ${target}:${dst}"
    return 0
  fi
  
  # Try rsync first
  if isCommand rsync; then
    rsync -avP --partial --inplace --no-perms --no-owner --no-group \
      -e "ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY}" \
      "$src" "$target:$dst/"
  else
    # Fallback to scp
    scp "${SSH_OPTS[@]}" "$src" "$target:$dst/"
  fi
}

# Write file to remote using heredoc
writeRemoteFile() {
  local target="$1"
  local remote_path="$2"
  local content="$3"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} would write remote file: ${remote_path}"
    return 0
  fi
  
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "$target" "cat > ${remote_path} <<'EOF'
${content}
EOF
chmod +x ${remote_path}
"
  log "...wrote ${remote_path}"
}

# Check SSH connectivity
checkSshConnectivity() {
  local target="$1"
  
  log "checking ssh connectivity..."
  
  if ssh "${SSH_OPTS[@]}" "$target" "echo connected && uname -a" >/dev/null 2>&1; then
    log "...connected"
    return 0
  else
    die "could not connect to ${target}:${SSH_PORT}"
  fi
}
