#!/usr/bin/env bash
# lib/conda.sh
# Conda environment management helpers (remote-safe)

: "${CONDA_DIR:?CONDA_DIR must be set}"

resolveCondaExe() {
  local condaDir="$1"

  local candidates=(
    "${condaDir}/condabin/conda"
    "${condaDir}/bin/conda"
    "${condaDir}/_conda"
  )

  local c
  for c in "${candidates[@]}"; do
    if runCmdReadOnly /usr/bin/test -x "$c"; then
      echo "$c"
      return 0
    fi
  done

  return 1
}

# ------------------------------------------------------------
# internal helper: run conda in a single remote shell
# (works for pipelines because it executes under bash -lc)
# ------------------------------------------------------------
_condaExec() {
  local condaExe
  condaExe="$(resolveCondaExe "$CONDA_DIR" 2>/dev/null || true)"

  if [[ -z "${condaExe:-}" ]]; then
    error "conda executable not found in ${CONDA_DIR}"
    return 1
  fi

  # _condaExec expects a conda *fragment* (string) so pipelines work.
  # Example:
  #   _condaExec "env list | awk '{print \$1}' | grep -qx 'runpod'"
  local fragment="$*"
  runSh "$(printf "%q " "${condaExe}") ${fragment}"
}

# Read-only conda execution for dry run mode
_condaExecReadOnly() {
  local condaExe
  condaExe="$(resolveCondaExe "$CONDA_DIR" 2>/dev/null || true)"

  if [[ -z "${condaExe:-}" ]]; then
    return 1
  fi

  local fragment="$*"
  runShReadOnly "$(printf "%q " "${condaExe}") ${fragment}"
}

# ------------------------------------------------------------
# ensure conda is installed at conda_dir (idempotent)
# IMPORTANT: do NOT run conda update here (ToS may not be accepted yet)
# ------------------------------------------------------------
ensureConda() {
  logTask "ensuring conda installation at ${CONDA_DIR}"

  local condaExe=""
  condaExe="$(resolveCondaExe "$CONDA_DIR" 2>/dev/null || true)"

  local installer="/tmp/miniconda.sh"
  local url="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"

  # if conda exists but is missing exec bit, fix it once
  if [[ -n "${condaExe:-}" ]] && runShReadOnly "test -f '${condaExe}' && ! test -x '${condaExe}'"; then
    warn "conda exists but is not executable; chmod +x"
    runSh "chmod +x '${condaExe}' || true"
  fi

  # healthy? Check using read-only in dry run
  if [[ -n "${condaExe:-}" ]]; then
    if [[ "${DRY_RUN:-0}" == "1" ]]; then
      # In dry run, just check if file exists
      if runCmdReadOnly test -x "$condaExe"; then
        log "conda already installed: ${CONDA_DIR}"
        return 0
      fi
    else
      # Normal check with version command
      if runCmd "$condaExe" --version >/dev/null 2>&1; then
        log "conda already installed: ${CONDA_DIR}"
        return 0
      fi
    fi
  fi

  # partial?
  if runShReadOnly "test -e '${CONDA_DIR}'"; then
    warn "conda directory exists but install looks incomplete: ${CONDA_DIR}"
  fi

  logAction "downloading miniconda installer"
  runCmd wget -q "$url" -O "$installer"

  logAction "installing/updating miniconda (-u)"
  if runCmd bash "$installer" -b -p "${CONDA_DIR}" -u; then
    log "conda update-in-place succeeded"
    :
  else
    warn "conda update-in-place failed, wiping and reinstalling..."
    runCmd rm -rf "${CONDA_DIR}"
    runCmd bash "$installer" -b -p "${CONDA_DIR}"
  fi
  runCmd rm -f "$installer"

  # refresh conda path after installation
  condaExe="$(resolveCondaExe "$CONDA_DIR" 2>/dev/null || true)"

  # verify
  if [[ -z "${condaExe:-}" ]] || ! runCmd "$condaExe" --version >/dev/null 2>&1; then
    runSh "ls -la '${CONDA_DIR}' || true"
    runSh "ls -la '${CONDA_DIR}/bin' || true"
    runSh "ls -la '${CONDA_DIR}/condabin' || true"
    error "conda install failed: ${CONDA_DIR}"
    return 1
  fi

  log "conda installed at: ${CONDA_DIR}"
  return 0
}

# ------------------------------------------------------------
# configure conda channels (remote-safe)
# ------------------------------------------------------------
ensureCondaChannels() {
  log "configuring conda channels"

  # remove-key returns non-zero if missing; keep behaviour
  _condaExec "config --remove-key channels 2>/dev/null || true"
  _condaExec "config --add channels conda-forge"
  _condaExec "config --set channel_priority strict"

  log "channels configured"
  return 0
}

# ------------------------------------------------------------
# accept conda ToS (remote-safe)
# ------------------------------------------------------------
acceptCondaTos() {
  log "accepting conda terms of service"

  # keep these as single-line strings
  _condaExec "tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true"
  _condaExec "tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true"
  return 0
}

# ------------------------------------------------------------
# update base conda (safe to call AFTER ToS acceptance)
# ------------------------------------------------------------
updateCondaBase() {
  log "updating conda base"
  _condaExec "update -y -n base -c defaults conda || true"
  return 0
}

# ------------------------------------------------------------
# ensure conda configuration (remote-safe)
# ------------------------------------------------------------
ensureCondaConfiguration() {
  log "conda configuration"
  _condaExec "info"
  _condaExec "config --show channels"
  return 0
}

# ------------------------------------------------------------
# ensure env exists (remote-safe, idempotent)
# ------------------------------------------------------------
ensureCondaEnv() {
  local env_name="${1:-runpod}"
  local python_version="${2:-3.10}"

  # Check if env exists (use read-only exec for dry run compatibility)
  if _condaExecReadOnly "env list | awk '{print \$1}' | grep -qx '${env_name}'"; then
    log "conda environment exists: ${env_name}"
    return 0
  fi

  logAction "creating conda environment: ${env_name}"
  _condaExec "create -n '${env_name}' python='${python_version}' -y"
  log "environment created"
  return 0
}

# ------------------------------------------------------------
# run a command inside a conda env (remote-safe)
# ------------------------------------------------------------
condaEnvSh() {
  local env="$1"
  shift
  local script="$1"

  if [[ -z "${env:-}" ]]; then
    error "condaEnvSh called without env"
    return 1
  fi
  if [[ -z "${script:-}" ]]; then
    error "condaEnvSh called without a script"
    return 1
  fi

  local condaExe
  condaExe="$(resolveCondaExe "$CONDA_DIR" 2>/dev/null || true)"
  if [[ -z "${condaExe:-}" ]]; then
    error "conda executable not found in ${CONDA_DIR}"
    return 1
  fi

  echo "Running in conda env '${env}': ${script}"
  runCmd "${condaExe}" run -n "${env}" --no-capture-output bash -lc "${script}"
}

condaEnvCmd() {
  local envName="$1"
  shift

  if [[ -z "${envName:-}" ]]; then
    error "condaEnvCmd: environment name not provided"
    return 1
  fi

  local condaExe
  condaExe="$(resolveCondaExe "$CONDA_DIR" 2>/dev/null || true)"

  if [[ -z "${condaExe:-}" ]]; then
    error "conda executable not found in ${CONDA_DIR}"
    return 1
  fi

  log "Running in conda env '${envName}': $*"

  # argv-safe: no shell, no temp scripts, no quoting games
  runCmd "${condaExe}" run -n "${envName}" --no-capture-output "$@"
}
