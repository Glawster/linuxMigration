#!/usr/bin/env bash
# lib/apt.sh
# APT package management helpers

# Ensure apt packages are installed
ensureAptPackages() {
  if ! isCommand apt-get; then
    warn "apt-get not found. Assuming base image has required tools."
    return 0
  fi
  
  log "ensuring base tools via apt"
  
  # Set environment for non-interactive apt
  export DEBIAN_FRONTEND=noninteractive
  export TZ=Etc/UTC
  export LANG=C.UTF-8
  export LC_ALL=C.UTF-8
  
  # Clean apt locks before update
  log "cleaning apt locks"
  rm -f /var/lib/apt/lists/lock 2>/dev/null || true
  rm -f /var/cache/apt/archives/lock 2>/dev/null || true
  rm -f /var/lib/dpkg/lock* 2>/dev/null || true
  
  run apt-get update -y
  run apt-get install -y \
    git \
    wget \
    rsync \
    tmux \
    htop \
    unzip \
    build-essential \
    python3-venv \
    python3-pip \
    ca-certificates \
    vim
}
