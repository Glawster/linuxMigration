#!/usr/bin/env bash
# steps/30_conda.sh
# Setup conda environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"

main() {

  # Check if already done and not forcing
  if isStepDone "CONDA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "conda already configured (use --force to rerun)"
    return 0
  fi

  ensureConda "$CONDA_DIR"
  ensureCondaChannels "$CONDA_DIR"
  acceptCondaTos "$CONDA_DIR"
  ensureCondaEnv "$CONDA_DIR" "$ENV_NAME" "3.10"

  # Show conda info (must be in one remote shell)
  log "conda configuration"
  run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda info"
  run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda config --show channels"

  markStepDone "CONDA"
  log "done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
