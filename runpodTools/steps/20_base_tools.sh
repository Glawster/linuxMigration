#!/usr/bin/env bash
# steps/20_base_tools.sh
# Install base system tools

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/apt.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  log "step: base tools"
  
  # Check if already done and not forcing
  if isStepDone "BASE_TOOLS" && [[ "${FORCE:-0}" != "1" ]]; then
    log "...base tools already installed (use --force to rerun)"
    return 0
  fi
  
  # Check GPU
  log "checking gpu"
  if isCommand nvidia-smi; then
    run nvidia-smi || true
  else
    warn "nvidia-smi not found"
  fi
  
  # Install packages
  ensureAptPackages
  
  markStepDone "BASE_TOOLS"
  log "...base tools done"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
