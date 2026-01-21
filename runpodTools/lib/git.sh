#!/usr/bin/env bash
# lib/git.sh
# Git repository management helpers

# Ensure git repository is cloned and up to date (idempotent)
ensureGitRepo() {
  local dir="$1"
  local url="$2"
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    # If it's a valid git repo, pull
    if [[ -d "$dir/.git" ]]; then
      log "...repo exists, pulling: $dir"
      if [[ "${DRY_RUN:-0}" == "1" ]]; then
        echo "${DRY_PREFIX:-...[]} git -C $dir fetch --all --prune"
        echo "${DRY_PREFIX:-...[]} git -C $dir pull --ff-only"
      else
        git -C "$dir" fetch --all --prune 2>/dev/null || true
        git -C "$dir" pull --ff-only 2>/dev/null || true
      fi
      return 0
    fi
    
    # If directory exists but not a git repo, move aside
    if [[ -d "$dir" ]]; then
      moveAside "$dir"
    fi
    
    # Clone the repo
    log "...cloning: $url -> $dir"
    run git clone "$url" "$dir"
  else
    # Remote execution via SSH
    if runRemote "$SSH_TARGET" "test -d '$dir/.git'" 2>/dev/null; then
      log "...repo exists on remote, pulling: $dir"
      runRemote "$SSH_TARGET" "cd '$dir' && git fetch --all --prune 2>/dev/null || true && git pull --ff-only 2>/dev/null || true"
      return 0
    fi
    
    # If directory exists but not a git repo, move aside
    if runRemote "$SSH_TARGET" "test -d '$dir'" 2>/dev/null; then
      local backup="${dir}.backup.$(timestamp)"
      warn "Moving aside on remote: $dir -> $backup"
      runRemote "$SSH_TARGET" "mv '$dir' '$backup'"
    fi
    
    # Clone the repo
    log "...cloning on remote: $url -> $dir"
    runRemote "$SSH_TARGET" "git clone '$url' '$dir'"
  fi
}
