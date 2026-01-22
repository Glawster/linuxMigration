#!/usr/bin/env bash
# lib/conda.sh
# Conda environment management helpers (remote-safe)
#
# Rule:
#   - never call `source` or `conda` locally
#   - always go through: run bash -lc "source ... && conda ..."

set -euo pipefail

resolveCondaExe() {
  local condaDir="$1"

  if run bash -lc "test -x '${condaDir}/condabin/conda'"; then
    echo "${condaDir}/condabin/conda"
    return 0
  fi

  if run bash -lc "test -x '${condaDir}/bin/conda'"; then
    echo "${condaDir}/bin/conda"
    return 0
  fi

  if run bash -lc "test -x '${condaDir}/_conda'"; then
    echo "${condaDir}/_conda"
    return 0
  fi

  return 1
}

# ------------------------------------------------------------
# internal helper: run conda in a single remote shell
# ------------------------------------------------------------
_condaExec() {
  local conda_dir="$1"
  shift

  local condaExe
  condaExe="$(resolveCondaExe "$conda_dir" 2>/dev/null || true)"

  if [[ -z "${condaExe:-}" ]]; then
    error "conda executable not found in ${conda_dir}"
    return 1
  fi

  run bash -lc "'${condaExe}' $*"
}

# ------------------------------------------------------------
# ensure conda is installed at CONDA_DIR (idempotent + self-healing)
# ------------------------------------------------------------
ensureConda() {
  # supports being called as: ensureConda "$CONDA_DIR"
  # but defaults to global CONDA_DIR if not supplied
  local conda_dir="${1:-${CONDA_DIR}}"
  if [[ -z "${conda_dir:-}" ]]; then
    error "CONDA_DIR not set"
    return 1
  fi

  logTask "ensuring conda installation at ${conda_dir}"

  local conda_bin=""
  conda_bin="$(resolveCondaExe "$conda_dir" 2>/dev/null || true)"

  local installer="/tmp/miniconda.sh"
  local url="https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"

  # healthy?
  # if conda exists but is missing exec bit, fix it once
  if [[ -n "${conda_bin:-}" ]] && run bash -lc "test -f '${conda_bin}' && ! test -x '${conda_bin}'"; then
    warn "conda exists but is not executable; chmod +x"
    run bash -lc "chmod +x '${conda_bin}' || true"
  fi

  if [[ -n "$conda_bin" ]] && run bash -lc "'${conda_bin}' --version >/dev/null 2>&1"; then
    log "conda already installed: ${conda_dir}"
    run "${conda_bin}" update -y -n base -c defaults conda || true
    return 0
  fi

  # partial?
  if run bash -lc "test -e '${conda_dir}'"; then
    warn "conda directory exists but install looks incomplete: ${conda_dir}"
  fi

  log "downloading miniconda installer"
  run wget -q "$url" -O "$installer"

  log "installing/updating miniconda (-u)"
  if run bash "$installer" -b -u -p "${conda_dir}"; then
    :
  else
    warn "conda update-in-place failed, wiping and reinstalling..."
    run rm -rf "${conda_dir}"
    run bash "$installer" -b -p "${conda_dir}"
  fi

  run rm -f "$installer"
  # refresh conda path after installation
  conda_bin="$(resolveCondaExe "$conda_dir" 2>/dev/null || true)"

  if [[ -z "${conda_bin:-}" ]] || ! run bash -lc "'${conda_bin}' --version >/dev/null 2>&1"; then
    run bash -lc "ls -la '${conda_dir}' || true"
    run bash -lc "ls -la '${conda_dir}/bin' || true"
    run bash -lc "ls -la '${conda_dir}/condabin' || true"
    error "conda install failed: ${conda_dir}"
    return 1
  fi

  log "conda installed at: ${conda_dir}"
}

# ------------------------------------------------------------
# configure conda channels (remote-safe)
# ------------------------------------------------------------
ensureCondaChannels() {
  local conda_dir="${1:-${CONDA_DIR}}"
  if [[ -z "${conda_dir:-}" ]]; then
    error "CONDA_DIR not set"
    return 1
  fi

  log "configuring conda channels"

  # remove-key returns non-zero if missing; keep your behaviour
  _condaExec "$conda_dir" "config --remove-key channels 2>/dev/null || true"
  _condaExec "$conda_dir" "config --add channels conda-forge"
  _condaExec "$conda_dir" "config --set channel_priority strict"

  log "channels configured"
}

# ------------------------------------------------------------
# accept conda ToS (remote-safe)
# ------------------------------------------------------------
acceptCondaTos() {
  local conda_dir="${1:-${CONDA_DIR}}"
  if [[ -z "${conda_dir:-}" ]]; then
    error "CONDA_DIR not set"
    return 1
  fi

  log "accepting conda terms of service"

  _condaExec "$conda_dir" "tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main 2>/dev/null || true"
  _condaExec "$conda_dir" "tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r 2>/dev/null || true"
}

# ------------------------------------------------------------
# ensure env exists (remote-safe, idempotent)
# ------------------------------------------------------------
ensureCondaEnv() {
  local conda_dir="${1:-${CONDA_DIR}}"
  local env_name="${2:-runpod}"
  local python_version="${3:-3.10}"

  if [[ -z "${conda_dir:-}" ]]; then
    error "CONDA_DIR not set"
    return 1
  fi

  # Check if env exists
  if _condaExec "$conda_dir" "env list | awk '{print \$1}' | grep -qx '${env_name}'"; then
    log "conda environment exists: ${env_name}"
    return 0
  fi

  log "creating conda environment: ${env_name}"
  _condaExec "$conda_dir" "create -n '${env_name}' python='${python_version}' -y"
  log "environment created"
}

condaEnvRun() {
  local env="$1"
  shift
  run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${env}' && $*"
}
