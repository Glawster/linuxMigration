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

main() {
 
  # Create bash aliases
  log "creating /root/.bash_aliases"
  runSh "echo \"alias d='ls -al'\" >> ~/.bash_aliases"

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
  log "base tools done\n"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
