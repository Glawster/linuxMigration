#!/usr/bin/env bash
# lib/git.sh
# Git repository management helpers

set -euo pipefail

# Move an existing directory aside on the REMOTE host
# Result: <dir>.bak.<timestamp>
moveAside() {
  local dir="$1"
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"

  local bak="${dir}.bak.${ts}"
  warn "moving aside: ${dir} -> ${bak}"
  run mv "$dir" "$bak"
}

# Ensure a git repository is cloned and up to date (idempotent, remote-safe)
ensureGitRepo() {
  local dir="$1"
  local url="$2"

  # If it's a valid git repo, update and return
  if run test -d "${dir}/.git"; then
    log "repo exists, pulling: ${dir}"
    run git -C "${dir}" fetch --all --prune
    run git -C "${dir}" pull --ff-only
    return 0
  fi

  # If directory exists but not a git repo
  if run test -d "${dir}"; then
    if [[ "${FORCE:-0}" == "1" ]]; then
      warn "forcing removal of existing directory: ${dir}"
      run rm -rf "${dir}"
    else
      moveAside "${dir}"
    fi
  fi

  # Clone the repo
  log "cloning: ${url} -> ${dir}"
  run git clone "${url}" "${dir}"
  return 0
}
