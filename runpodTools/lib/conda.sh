#!/usr/bin/env bash
# lib/conda.sh
# Conda environment management helpers

# Ensure miniconda is installed
ensureMiniconda() {
  local conda_dir="${1:-/workspace/miniconda3}"
  
  # Check if conda already exists
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local check
    if [[ -x "$conda_dir/bin/conda" ]]; then
      log "...miniconda already installed at $conda_dir"
      return 0
    fi
  else
    # Remote check
    if runRemote "$SSH_TARGET" "test -x '$conda_dir/bin/conda'" 2>/dev/null; then
      log "...miniconda already installed on remote at $conda_dir"
      return 0
    fi
  fi
  
  log "installing miniconda to $conda_dir"
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    run wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
    run bash /tmp/miniconda.sh -b -p "$conda_dir"
    run rm -f /tmp/miniconda.sh
  else
    # Remote execution
    runRemoteHeredoc <<EOF
wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /tmp/miniconda.sh
bash /tmp/miniconda.sh -b -p "$conda_dir"
rm -f /tmp/miniconda.sh
EOF
  fi
  
  log "...miniconda installed"
}

# Configure conda channels for resilience
ensureCondaChannels() {
  local conda_dir="${1:-/workspace/miniconda3}"
  
  log "configuring conda channels"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} conda config --remove-key channels"
    echo "${DRY_PREFIX:-...[]} conda config --add channels conda-forge"
    echo "${DRY_PREFIX:-...[]} conda config --set channel_priority strict"
    return 0
  fi
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    # shellcheck disable=SC1090
    source "$conda_dir/etc/profile.d/conda.sh"
    
    conda config --remove-key channels 2>/dev/null || true
    conda config --add channels conda-forge
    conda config --set channel_priority strict
  else
    # Remote execution
    runRemoteHeredoc <<EOF
source "$conda_dir/etc/profile.d/conda.sh"
conda config --remove-key channels 2>/dev/null || true
conda config --add channels conda-forge
conda config --set channel_priority strict
EOF
  fi
  
  log "...channels configured"
}

# Accept conda ToS
acceptCondaTos() {
  local conda_dir="${1:-/workspace/miniconda3}"
  
  log "accepting conda terms of service"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} conda tos accept"
    return 0
  fi
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    # shellcheck disable=SC1090
    source "$conda_dir/etc/profile.d/conda.sh"
    
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
    conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true
  else
    # Remote execution
    runRemoteHeredoc <<EOF
source "$conda_dir/etc/profile.d/conda.sh"
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true
EOF
  fi
}

# Ensure conda environment exists
ensureCondaEnv() {
  local conda_dir="${1:-/workspace/miniconda3}"
  local env_name="${2:-runpod}"
  local python_version="${3:-3.10}"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} would ensure conda env: $env_name"
    return 0
  fi
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    # shellcheck disable=SC1090
    source "$conda_dir/etc/profile.d/conda.sh"
    
    if conda env list | awk '{print $1}' | grep -qx "$env_name"; then
      log "...conda environment exists: $env_name"
    else
      log "creating conda environment: $env_name"
      conda create -n "$env_name" python="$python_version" -y
      log "...environment created"
    fi
    
    conda activate "$env_name"
    log "...activated conda environment: $env_name"
  else
    # Remote execution
    runRemoteHeredoc <<EOF
source "$conda_dir/etc/profile.d/conda.sh"

if conda env list | awk '{print \$1}' | grep -qx "$env_name"; then
  echo "...conda environment exists: $env_name"
else
  echo "creating conda environment: $env_name"
  conda create -n "$env_name" python="$python_version" -y
  echo "...environment created"
fi

conda activate "$env_name"
echo "...activated conda environment: $env_name"
EOF
  fi
}

# Activate conda environment
activateCondaEnv() {
  local conda_dir="${1:-/workspace/miniconda3}"
  local env_name="${2:-runpod}"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} source $conda_dir/etc/profile.d/conda.sh"
    echo "${DRY_PREFIX:-...[]} conda activate $env_name"
    return 0
  fi
  
  if [[ -z "${SSH_TARGET:-}" ]]; then
    # Local execution
    # shellcheck disable=SC1090
    source "$conda_dir/etc/profile.d/conda.sh"
    conda activate "$env_name"
  else
    # Remote execution - just log it, actual activation happens in the remote shell
    log "...will activate conda environment $env_name on remote"
  fi
}
