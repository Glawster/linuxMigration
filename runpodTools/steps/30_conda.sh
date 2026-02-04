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
# shellcheck disable=SC1091
source "$LIB_DIR/run.sh"

condaDiagnostics() {
  log "conda diagnostics"

  log "who am i / id / hostname / pwd"
  runSh "whoami; id; hostname; pwd" || true

  log "disk usage"
  runSh "df -h / /workspace 2>/dev/null || true" || true

  log "mounts"
  runSh "mount | grep -E ' /workspace | / ' || true" || true

  log "conda directory listing"
  runSh "echo 'CONDA_DIR=${CONDA_DIR:-}'" || true

  log "listing conda directory contents"
  runSh "ls -la '${CONDA_DIR}' || true" || true

  log "listing conda subdirectories"
  runSh "ls -la '${CONDA_DIR}/bin' || true" || true

  log "listing condabin"
  runSh "ls -la '${CONDA_DIR}/condabin' || true" || true

  log "checking for conda executables"
  runSh "test -x '${CONDA_DIR}/condabin/conda' && '${CONDA_DIR}/condabin/conda' --version || true" || true
  runSh "test -x '${CONDA_DIR}/bin/conda' && '${CONDA_DIR}/bin/conda' --version || true" || true
  runSh "test -x '${CONDA_DIR}/_conda' && '${CONDA_DIR}/_conda' --version || true" || true

  log "scanning for conda binaries under CONDA_DIR"
  runSh "find '${CONDA_DIR}' -maxdepth 4 -type f -name conda -print 2>/dev/null | head -n 50 || true" || true
}

main() {

  if isStepDone "CONDA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "conda already configured (use --force to rerun)"
    return 0
  fi

  if ! ensureConda ; then
    #condaDiagnostics
    die "conda install failed"
  fi

  # Accept ToS early to prevent CondaToSNonInteractiveError during any subsequent ops
  if ! acceptCondaTos ; then
    #condaDiagnostics
    die "conda tos accept failed"
  else
    markStepDone "CONDA_TOS"
  fi

  # Now safe to update base conda if you still want it
  updateCondaBase || true

  if ! ensureCondaChannels ; then
    #condaDiagnostics
    die "conda channel configuration failed"
  else
    markStepDone "CONDA_CHANNELS"
  fi

  if ! ensureCondaEnv "$ENV_NAME"; then
    #condaDiagnostics
    die "conda env setup failed"
  fi

  if ! ensureCondaConfiguration "$ENV_NAME"; then
    #condaDiagnostics
    die "conda configuration failed"
  fi  

  markStepDone "CONDA"
  log "done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
