#!/usr/bin/env bash
# lib/common.sh
# Common logging helpers and utility functions

# Logging functions
log() {
  echo -e "\n==> $*\n"
}

warn() {
  echo -e "\nWARNING: $*\n" >&2
}

error() {
  echo -e "\nERROR: $*\n" >&2
}

die() {
  error "$@"
  exit 1
}

# Run command with dry-run support
run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} $*"
  else
    "$@"
  fi
}

# Check if command exists
isCommand() {
  command -v "$1" >/dev/null 2>&1
}

# Ensure directory exists
ensureDir() {
  local dir="$1"
  if [[ ! -d "$dir" ]]; then
    run mkdir -p "$dir"
  fi
}

# Timestamp for logging
timestamp() {
  date +"%Y%m%d_%H%M%S"
}

# Move existing directory aside with timestamp
moveAside() {
  local dir="$1"
  local backup="${dir}.backup.$(timestamp)"
  
  if [[ -d "$dir" ]]; then
    warn "Moving aside: $dir -> $backup"
    run mv "$dir" "$backup"
  fi
}
