#!/usr/bin/env bash
# steps/20_base_tools.sh
# Install base system tools

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/apt.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

setupSharedCaches() {
  # run once (independent of BASE_TOOLS)
  if isStepDone "CACHE_SETUP" && [[ "${FORCE:-0}" != "1" ]]; then
    log "cache already set up"
    return 0
  fi

  log "setting up shared caches"

  # make cache dirs on workspace (persists for the pod lifetime)
  runSh "mkdir -p \
    /workspace/.cache/pip \
    /workspace/.cache/huggingface/transformers \
    /workspace/.cache/torch"

  # make env vars available to all future shells (and tmux sessions)
  runSh "mkdir -p /etc/profile.d"
  runSh "cat >/etc/profile.d/runpod_cache.sh <<'EOF'
export PIP_CACHE_DIR=/workspace/.cache/pip
export HF_HOME=/workspace/.cache/huggingface
export TRANSFORMERS_CACHE=/workspace/.cache/huggingface/transformers
export TORCH_HOME=/workspace/.cache/torch
EOF"
  runSh "chmod 0644 /etc/profile.d/runpod_cache.sh"

  markStepDone "CACHE_SETUP"
  log "cache set up"
}

main() {

  setupSharedCaches

  # Check if already done and not forcing
  if isStepDone "BASE_TOOLS" && [[ "${FORCE:-0}" != "1" ]]; then
    log "base tools already installed (use --force to rerun)"
    return 0
  fi
  
  # in base_tools step
  if isStepDone "GPU_CHECK" && [[ "${FORCE:-0}" != "1" ]]; then
    log "gpu already checked"
  else
    log "checking gpu"
    if command -v nvidia-smi >/dev/null 2>&1; then
      nvidia-smi
    else
      log "nvidia-smi not available"
    fi
    markStepDone "GPU_CHECK"
  fi

  # Install packages
  ensureAptPackages
  
  markStepDone "BASE_TOOLS"
  log "done"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
