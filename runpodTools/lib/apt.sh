#!/usr/bin/env bash
# lib/apt.sh
# APT package management helpers

# Ensure apt packages are installed
ensureAptPackages() {
  log "checking package manager"

  if ! runSh "command -v apt-get >/dev/null 2>&1"; then
    warn "apt-get not found. Assuming base image has required tools."
    return 0
  fi
  
  logTask "ensuring base tools via apt"
  
  # Set environment for non-interactive apt
  export DEBIAN_FRONTEND=noninteractive
  export TZ=Etc/UTC
  export LANG=C.UTF-8
  export LC_ALL=C.UTF-8
  
  if runSh "command -v apt-get >/dev/null 2>&1"; then
    log "ensuring base tools via apt-get"

    need=()
    for pkg in htop ca-certificates git rsync tmux unzip vim wget python3-pip python3-venv; do
      if ! runSh "dpkg -s \"$pkg\" >/dev/null 2>&1"; then
        need+=("$pkg")
      fi
    done

    if (( ${#need[@]} == 0 )) && [[ "${FORCE:-0}" != "1" ]]; then
      log "base tools already present"
    else
      log "installing base tools via apt-get: ${need[*]}"
      runCmd apt-get update
      runCmd apt-get install -y "${need[@]}"
    fi

  else
    warn "no apt-get available on this pod image, skipping system packages"
  fi

}
