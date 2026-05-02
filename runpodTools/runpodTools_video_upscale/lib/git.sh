#!/usr/bin/env bash
# lib/git.sh
# Git repository management helpers

# Move an existing directory aside on the REMOTE host
# Result: <dir>.bak.<timestamp>
moveAside() {
  local dir="$1"
  local ts
  ts="$(date +%Y%m%d_%H%M%S)"

  local bak="${dir}.bak.${ts}"
  warn "moving aside: ${dir} -> ${bak}"
  runCmd mv "$dir" "$bak"
}

ensureGitRepo() {
  local dir="$1"
  local url="$2"
  local name="$3"

  # If it's already a git repo, update in place
  if runCmd test -d "${dir}/.git"; then
    log "updating: ${name}: ${dir}"
    runSh "$(cat <<EOF
set -euo pipefail
cd '$dir'

# Make sure origin is correct (handles repos that were copied in)
current="\$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "\$current" ]]; then
  git remote add origin '$url'
elif [[ "\$current" != '$url' ]]; then
  git remote set-url origin '$url'
fi

git fetch --all --prune

# Pull the currently checked-out branch if possible; otherwise try main/master
branch="\$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ -z "\$branch" || "\$branch" == "HEAD" ]]; then
  branch="main"
fi

git pull --ff-only origin "\$branch" \
  || git pull --ff-only origin main \
  || git pull --ff-only origin master
EOF
)"
    return 0
  fi

  # If the directory exists but isn't a git repo, move it aside safely
  if runCmd test -e "$dir"; then
    local ts
    ts="$(date +%Y%m%d_%H%M%S)"
    log "ERROR destination exists and is not a git repo: ${dir}"
    log "moving aside: ${dir} -> ${dir}.bak_${ts}"
    runCmd mv "$dir" "${dir}.bak_${ts}"
  fi

  # Fresh clone
  log "cloning: ${url} -> ${dir}"
  runCmd git clone "$url" "$dir"
}

