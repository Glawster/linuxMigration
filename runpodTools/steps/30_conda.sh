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

condaDiagnostics() {
  log "conda diagnostics"
  
  log "who am i / id / hostname / pwd"
  run bash -lc "whoami; id; hostname; pwd"
  log "disk usage"
  run bash -lc "df -h / /workspace 2>/dev/null || true"
  log "mounts"
  run bash -lc "mount | grep -E ' /workspace | / ' || true"
  log "conda directory listing"
  run bash -lc "echo 'CONDA_DIR=${CONDA_DIR:-}'"
  log "listing conda directory contents"
  run bash -lc "ls -la '${CONDA_DIR}' || true"
  log "listing conda subdirectories"
  run bash -lc "ls -la '${CONDA_DIR}/bin' || true"
  log "listing condabin and profile.d"
  run bash -lc "ls -la '${CONDA_DIR}/condabin' || true"
  log "listing profile.d"
  run bash -lc "ls -la '${CONDA_DIR}/etc/profile.d' || true"

  # show conda entrypoints if they exist
  log "checking for conda executables"
  run bash -lc "test -x '${CONDA_DIR}/condabin/conda' && '${CONDA_DIR}/condabin/conda' --version || true"
  log "checking for conda executables 2"
  run bash -lc "test -x '${CONDA_DIR}/bin/conda' && '${CONDA_DIR}/bin/conda' --version || true"
  log "checking for conda executables 3"
  run bash -lc "test -x '${CONDA_DIR}/_conda' && '${CONDA_DIR}/_conda' --version || true"

  # is conda in PATH in a plain shell?
  log "checking if conda is in PATH"
  #run bash -lc "if command -v conda >/dev/null 2>&1; then conda --version; else echo 'conda not on PATH'; fi"

  # quick scan for conda binary inside the prefix
  log "scanning for conda binaries under CONDA_DIR"
  run bash -lc "find '${CONDA_DIR}' -maxdepth 4 -type f -name conda -print 2>/dev/null | head -n 50 || true"
}

main() {

  # Check if already done and not forcing
  if isStepDone "CONDA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "conda already configured (use --force to rerun)"
    return 0
  fi

  if ! ensureConda "$CONDA_DIR"; then
    condaDiagnostics
    die "conda install failed"
  fi

  if ! ensureCondaChannels "$CONDA_DIR"; then
    condaDiagnostics
    die "conda channel configuration failed"
  fi

  if ! acceptCondaTos "$CONDA_DIR"; then
    condaDiagnostics
    die "conda tos accept failed"
  fi

  if ! ensureCondaEnv "$CONDA_DIR" "$ENV_NAME" "3.10"; then
    condaDiagnostics
    die "conda env setup failed"
  fi

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
