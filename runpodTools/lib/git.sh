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
  run mv "$dir" "$bak"
}

# Ensure a git repository is cloned and up to date (idempotent, remote-safe)
ensureGitRepo-old() {
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

# Ensure a git repository is present and updated to upstream snapshot
# - Never reclones if .git exists
# - Detached-HEAD safe
# - No merges, no pull
# - Idempotent and remote-safe
ensureGitRepo() {
  local dir="$1"
  local url="$2"

  # Repo exists
  if run test -d "${dir}/.git"; then
    log "repo exists, syncing snapshot: ${dir}"

    # Sanity check: is this a usable work-tree?
    if ! run git -C "${dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      warn "WARNING: unusable git repo detected: ${dir}"
      if [[ "${FORCE:-0}" == "1" ]]; then
        warn "forcing removal of unusable repo: ${dir}"
        run rm -rf "${dir}"
      else
        moveAside "${dir}"
      fi
      # fall through to clone
    else
      # Fetch repairs most partial-clone states
      run git -C "${dir}" fetch --all --prune

      # Determine upstream default branch via origin/HEAD
      local defaultRef
      defaultRef="$(runCapture git -C "${dir}" symbolic-ref -q refs/remotes/origin/HEAD 2>/dev/null || true)"

      if [[ -z "${defaultRef}" ]]; then
        # Fallbacks if origin/HEAD missing
        if run git -C "${dir}" show-ref --verify --quiet refs/remotes/origin/master; then
          defaultRef="refs/remotes/origin/master"
        elif run git -C "${dir}" show-ref --verify --quiet refs/remotes/origin/main; then
          defaultRef="refs/remotes/origin/main"
        else
          warn "WARNING: cannot determine upstream branch, skipping update: ${dir}"
          return 0
        fi
      fi

      local branch="${defaultRef##refs/remotes/origin/}"

      log "...resetting to upstream snapshot: origin/${branch}"

      # Snapshot update (no merge, no pull)
      run git -C "${dir}" checkout -B "${branch}" "origin/${branch}"
      run git -C "${dir}" reset --hard "origin/${branch}"
      run git -C "${dir}" clean -fd

      return 0
    fi
  fi

  # Directory exists but is not a git repo
  if run test -d "${dir}"; then
    if [[ "${FORCE:-0}" == "1" ]]; then
      warn "forcing removal of existing directory: ${dir}"
      run rm -rf "${dir}"
    else
      moveAside "${dir}"
    fi
  fi

  # Clone fresh
  log "cloning: ${url} -> ${dir}"
  run git clone "${url}" "${dir}"
  return 0
}
