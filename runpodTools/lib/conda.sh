#!/usr/bin/env bash
# ------------------------------------------------------------
# conda helpers (modular: runCmd/runSh only)
# ------------------------------------------------------------

set -euo pipefail

# expects these to be available from your standard sourcing chain:
# - log, warn, error
# - runCmd, runSh
# - CONDA_DIR
# - ENV_NAME (optional usage)
# - WORKSPACE_ROOT (optional usage)

# cache
_CONDA_EXE=""

condaExe() {
  if [[ -n "${_CONDA_EXE}" ]]; then
    printf '%s' "${_CONDA_EXE}"
    return 0
  fi

  # prefer configured CONDA_DIR
  if [[ -n "${CONDA_DIR:-}" ]]; then
    if [[ -x "${CONDA_DIR}/bin/conda" ]]; then
      _CONDA_EXE="${CONDA_DIR}/bin/conda"
      printf '%s' "${_CONDA_EXE}"
      return 0
    fi
  fi

  # fallback to PATH
  if command -v conda >/dev/null 2>&1; then
    _CONDA_EXE="$(command -v conda)"
    printf '%s' "${_CONDA_EXE}"
    return 0
  fi

  return 1
}

ensureConda() {
  local conda_path=""

  # already available?
  if conda_path="$(condaExe 2>/dev/null)"; then
    # If file exists but isn’t executable, fix it (rare but happens after copy)
    if runSh "test -f '${conda_path}' && ! test -x '${conda_path}'"; then
      warn "conda exists but is not executable; chmod +x"
      runSh "chmod +x '${conda_path}' || true"
    fi

    if runCmd "${conda_path}" --version >/dev/null 2>&1; then
      log "conda already installed: ${conda_path}"
      return 0
    fi
  fi

  # if you have an installer path in your project, call it here.
  # keeping this conservative because your repo structure can vary.
  error "Conda not found. Expected CONDA_DIR/bin/conda or conda in PATH."
  return 1
}

# ------------------------------------------------------------
# conda environment execution
# ------------------------------------------------------------

condaEnvCmd() {
  # Executes a command by argv inside a conda env.
  # Usage: condaEnvCmd myenv python -V
  local env="$1"
  shift || true

  if [[ -z "${env}" ]]; then
    error "condaEnvCmd called without env"
    return 1
  fi
  if [[ $# -lt 1 ]]; then
    error "condaEnvCmd called without command"
    return 1
  fi

  ensureConda
  local conda_path
  conda_path="$(condaExe)"

  log "Running in conda env '${env}': $*"
  runCmd "${conda_path}" run -n "${env}" --no-capture-output "$@"
}

condaEnvSh() {
  # Executes a *shell script* inside a conda env (so cd/&& works).
  # Usage: condaEnvSh myenv "cd /x && python -m pip install -r requirements.txt"
  local env="$1"
  shift || true
  local script="${1:-}"

  if [[ -z "${env}" ]]; then
    error "condaEnvSh called without env"
    return 1
  fi
  if [[ -z "${script}" ]]; then
    error "condaEnvSh called without script"
    return 1
  fi

  ensureConda
  local conda_path
  conda_path="$(condaExe)"

  log "Running in conda env '${env}': ${script}"
  runCmd "${conda_path}" run -n "${env}" --no-capture-output bash -lc "${script}"
}

# ------------------------------------------------------------
# env management helpers
# ------------------------------------------------------------

condaEnsureEnv() {
  # Creates env if missing (idempotent)
  # Usage: condaEnsureEnv myenv python=3.10
  local env="$1"
  shift || true
  local spec=("$@")

  ensureConda
  local conda_path
  conda_path="$(condaExe)"

  if runCmd "${conda_path}" env list | awk '{print $1}' | grep -qx "${env}"; then
    log "conda env exists: ${env}"
    return 0
  fi

  if [[ ${#spec[@]} -eq 0 ]]; then
    # default if you don’t pass anything
    spec=("python=3.10")
  fi

  log "...creating conda env: ${env} (${spec[*]})"
  runCmd "${conda_path}" create -y -n "${env}" "${spec[@]}"
  log "conda env created: ${env}"
}
