#!/usr/bin/env bash
# steps/30_conda.sh
# Setup conda environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  log "step: conda"
  
  # Check if already done and not forcing
  if isStepDone "CONDA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "...conda already configured (use --force to rerun)"
    return 0
  fi
  
  ensureMiniconda "$CONDA_DIR"
  ensureCondaChannels "$CONDA_DIR"
  acceptCondaTos "$CONDA_DIR"
  ensureCondaEnv "$CONDA_DIR" "$ENV_NAME" "3.10"
  
  # Show conda info
  log "conda configuration"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} conda info"
    echo "${DRY_PREFIX:-...[]} conda config --show channels"
  else
    # shellcheck disable=SC1090
    source "$CONDA_DIR/etc/profile.d/conda.sh"
    conda info
    echo
    echo "--- Conda Channels ---"
    conda config --show channels
  fi
  
  markStepDone "CONDA"
  log "...conda done"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
