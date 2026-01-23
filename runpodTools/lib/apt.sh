#!/usr/bin/env bash
# lib/apt.sh
# APT package management helpers

# Ensure apt packages are installed
ensureAptPackages() {
  log "checking package manager"

  if ! isCommand apt-get; then
    warn "apt-get not found. Assuming base image has required tools."
    return 0
  fi
  
  logTask "ensuring base tools via apt"
  
  # Set environment for non-interactive apt
  export DEBIAN_FRONTEND=noninteractive
  export TZ=Etc/UTC
  export LANG=C.UTF-8
  export LC_ALL=C.UTF-8
  
  if hasCmd apt-get; then
    log "ensuring base tools via apt-get"

    run apt-get update -y
    run apt-get install -y \
      ca-certificates git wget unzip rsync tmux htop python3-pip python3-venv vim || true

  elif hasCmd apt; then
    log "ensuring base tools via apt"

    run apt update
    run apt install -y \
      ca-certificates git wget unzip rsync tmux htop python3-pip python3-venv vim || true

  else
    warn "no apt/apt-get available on this pod image, skipping system packages"
  fi

}
