#!/usr/bin/env bash
# lib/workspace.sh
# Common workspace paths and inventory helpers

set -euo pipefail

# ============================================================
# Workspace paths
# ============================================================
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
RUNPOD_DIR="${RUNPOD_DIR:-${WORKSPACE_ROOT}/runpodTools}"
CONDA_DIR="${CONDA_DIR:-${WORKSPACE_ROOT}/miniconda3}"
COMFY_DIR="${COMFY_DIR:-${WORKSPACE_ROOT}/ComfyUI}"
KOHYA_DIR="${KOHYA_DIR:-${WORKSPACE_ROOT}/kohya_ss}"
WORKFLOWS_DIR="${WORKFLOWS_DIR:-${WORKSPACE_ROOT}/workflows}"

# Default conda environment
ENV_NAME="${ENV_NAME:-runpod}"

# ============================================================
# Remote state tracking
# ============================================================
# State must live on the remote pod (NOT locally)
STATE_FILE="${RUNPOD_DIR}/state.env"

# Ensure remote directory exists (idempotent)
run mkdir -p "$(dirname "$STATE_FILE")" || true

# ------------------------------------------------------------
# isStepDone (REMOTE)
# ------------------------------------------------------------
isStepDone() {
  local step="$1"

  run bash -lc "set -e; test -f '${STATE_FILE}' || exit 1; \
    source '${STATE_FILE}'; \
    var='DONE_${step}'; \
    [[ \"\${!var:-0}\" == '1' ]]"
}

# ------------------------------------------------------------
# markStepDone (REMOTE)
# ------------------------------------------------------------
markStepDone() {
  local step="$1"
  log "marking step done: ${step}"

  run bash -lc "set -e; mkdir -p '$(dirname "$STATE_FILE")'; \
    if test -f '${STATE_FILE}'; then \
      if grep -q '^DONE_${step}=' '${STATE_FILE}'; then \
        sed -i 's/^DONE_${step}=.*/DONE_${step}=1/' '${STATE_FILE}'; \
      else \
        printf '%s\n' 'DONE_${step}=1' >> '${STATE_FILE}'; \
      fi; \
    else \
      printf '%s\n' 'DONE_${step}=1' > '${STATE_FILE}'; \
    fi"
}

# ------------------------------------------------------------
# showInventory (REMOTE)
# ------------------------------------------------------------
showInventory() {
  log "workspace inventory"

  run bash -lc "
    echo '--- Directories ---'
    ls -ld \
      '${WORKSPACE_ROOT}' \
      '${RUNPOD_DIR}' \
      '${CONDA_DIR}' \
      '${COMFY_DIR}' \
      '${KOHYA_DIR}' \
      '${WORKFLOWS_DIR}' \
      2>/dev/null || true
    echo

    echo '--- Conda Environments ---'
    if test -x '${CONDA_DIR}/condabin/conda'; then
      '${CONDA_DIR}/condabin/conda' env list 2>/dev/null || true
    elif test -x '${CONDA_DIR}/bin/conda'; then
      '${CONDA_DIR}/bin/conda' env list 2>/dev/null || true
    else
      echo 'Miniconda not installed'
    fi
    echo

    echo '--- State File ---'
    if test -f '${STATE_FILE}'; then
      cat '${STATE_FILE}'
    else
      echo 'No state file'
    fi
    echo
  "
}
