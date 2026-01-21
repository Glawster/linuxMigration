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

# Execute command (locally or remotely depending on SSH_TARGET)
# This is the key function that enables transparent local/remote execution
runCmd() {
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    run "$@"
  else
    # Remote execution
    runRemote "$SSH_TARGET" "$@"
  fi
}

# Run command on remote host
runRemote() {
  local target="$1"
  shift
  
  buildSshOpts
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} ssh ${SSH_OPTS[*]} ${target} $*"
    return 0
  fi
  
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "$target" "$@"
}

# Execute multi-line command on remote via heredoc
runRemoteHeredoc() {
  local target="${SSH_TARGET}"
  
  buildSshOpts
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} would ssh with heredoc to ${target}"
    cat
    return 0
  fi
  
  ssh "${SSH_OPTS[@]}" "$target" 'bash -s'
}

# Copy file to remote using rsync with fallback to scp
copyToRemote() {
  local src="$1"
  local target="$2"
  local dst="$3"
  
  buildSshOpts
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} rsync/scp $src -> ${target}:${dst}"
    return 0
  fi
  
  # Try rsync first
  if isCommand rsync; then
    # Build rsync SSH command from SSH_OPTS
    local rsync_ssh="ssh"
    for opt in "${SSH_OPTS[@]}"; do
      rsync_ssh="$rsync_ssh $opt"
    done
    
    rsync -avP --partial --inplace --no-perms --no-owner --no-group \
      -e "$rsync_ssh" \
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
  
  buildSshOpts
  
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
  
  buildSshOpts
  log "checking ssh connectivity..."
  
  if ssh "${SSH_OPTS[@]}" "$target" "echo connected && uname -a" >/dev/null 2>&1; then
    log "...connected"
    return 0
  else
    die "could not connect to ${target}:${SSH_PORT:-22}"
  fi
}

# Check if command exists (local or remote)
checkCommand() {
  local cmd="$1"
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    isCommand "$cmd"
  else
    runRemote "$SSH_TARGET" "command -v $cmd" >/dev/null 2>&1
  fi
}

# Check if directory exists (local or remote)
checkDir() {
  local dir="$1"
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    [[ -d "$dir" ]]
  else
    runRemote "$SSH_TARGET" "test -d '$dir'" >/dev/null 2>&1
  fi
}

# Check if file exists (local or remote)
checkFile() {
  local file="$1"
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    [[ -f "$file" ]]
  else
    runRemote "$SSH_TARGET" "test -f '$file'" >/dev/null 2>&1
  fi
}
