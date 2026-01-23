#!/usr/bin/env bash
# lib/apt.sh
# APT package management helpers

# Ensure apt packages are installed
ensureAptPackages() {
  log "checking package manager"

  run bash -lc "ls -la /usr/bin/apt-get /usr/bin/apt /bin/apt-get /bin/apt 2>/dev/null || true"
  run bash -lc "command -v apt-get || true"
  run bash -lc "command -v apt || true"

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

    run apt-get update
    run apt-get install -y \
      ca-certificates git wget unzip rsync tmux htop python3-pip python3-venv vim python3-pip || true

  elif hasCmd apt; then
    log "ensuring base tools via apt"

    run apt update
    run apt install -y \
      ca-certificates git wget unzip rsync tmux htop python3-pip python3-venv vim python3-pip || true

  else
    warn "no apt/apt-get available on this pod image, skipping system packages"
  fi

  #run apt-get update -y
  #run apt-get install -y \
  #  git \
    #wget \
    #rsync \
    #tmux \
    #htop \
    #unzip \
    #build-essential \
    #python3-venv \
    #python3-pip \
    #ca-certificates \
    #vim
}
