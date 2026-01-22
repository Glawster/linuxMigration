#!/usr/bin/env bash
# lib/git.sh
# Git repository management helpers

# Ensure git repository is cloned and up to date (idempotent)
ensureGitRepo() {
  local dir="$1"
  local url="$2"
  
  # If it's a valid git repo, pull
  if [[ -d "$dir/.git" ]]; then
    log "repo exists, pulling: $dir"
    run git -C "$dir" fetch --all --prune
    run git -C "$dir" pull --ff-only
  fi
  
  # If directory exists but not a git repo, move aside
  if [[ -d "$dir" ]]; then
    moveAside "$dir"
  fi
  
  # Clone the repo
  log "...cloning: $url -> $dir"
  run git clone "$url" "$dir"
}
