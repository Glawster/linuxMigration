#!/usr/bin/env bash
# lib/apt.sh
# APT package management helpers

# Ensure apt packages are installed
ensureAptPackages() {
  # Check if apt-get exists (locally or remotely)
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local check
    if ! isCommand apt-get; then
      warn "apt-get not found. Assuming base image has required tools."
      return 0
    fi
  else
    # Remote check
    if ! checkCommand apt-get; then
      warn "apt-get not found on remote. Assuming base image has required tools."
      return 0
    fi
  fi
  
  log "ensuring base tools via apt"
  
  # Set environment and run apt commands
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
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
  else
    # Remote execution via SSH
    runRemoteHeredoc <<'EOF'
export DEBIAN_FRONTEND=noninteractive
export TZ=Etc/UTC
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

echo "cleaning apt locks..."
rm -f /var/lib/apt/lists/lock 2>/dev/null || true
rm -f /var/cache/apt/archives/lock 2>/dev/null || true
rm -f /var/lib/dpkg/lock* 2>/dev/null || true

echo "running apt-get update..."
apt-get update -y

echo "installing packages..."
apt-get install -y \
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
EOF
  fi
}
