#!/usr/bin/env bash
# lib/workspace.sh
# Common workspace paths and inventory helpers

# Common paths
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/workspace}"
RUNPOD_DIR="${RUNPOD_DIR:-${WORKSPACE_ROOT}/runpodTools}"
CONDA_DIR="${CONDA_DIR:-${WORKSPACE_ROOT}/miniconda3}"
COMFY_DIR="${COMFY_DIR:-${WORKSPACE_ROOT}/ComfyUI}"
KOHYA_DIR="${KOHYA_DIR:-${WORKSPACE_ROOT}/kohya_ss}"
WORKFLOWS_DIR="${WORKFLOWS_DIR:-${WORKSPACE_ROOT}/workflows}"

# Default conda environment
ENV_NAME="${ENV_NAME:-runpod}"

# State file for tracking completed steps
STATE_FILE_DIR="/root/.runpodToolsState"
run mkdir -p "$STATE_FILE_DIR"
STATE_FILE="${RUNPOD_DIR}/state.env"

# Check if a step is marked as done
isStepDone() {
  local step="$1"
  
  if [[ ! -f "$STATE_FILE" ]]; then
    return 1
  fi
  
  # shellcheck disable=SC1090
  source "$STATE_FILE"
  
  local var_name="DONE_${step}"
  [[ "${!var_name:-0}" == "1" ]]
}

# Mark a step as done
markStepDone() {
  local step="$1"
  
  ensureDir "$(dirname "$STATE_FILE")"
  
  # Update or add the marker
  if [[ -f "$STATE_FILE" ]]; then
    if grep -q "^DONE_${step}=" "$STATE_FILE"; then
      sed -i "s/^DONE_${step}=.*/DONE_${step}=1/" "$STATE_FILE"
    else
      echo "DONE_${step}=1" >> "$STATE_FILE"
    fi
  else
    echo "DONE_${step}=1" > "$STATE_FILE"
  fi
}

# Inventory of workspace
showInventory() {
  log "workspace inventory"
  
  echo "--- Directories ---"
  ls -ld "$WORKSPACE_ROOT" "$RUNPOD_DIR" "$CONDA_DIR" "$COMFY_DIR" "$KOHYA_DIR" "$WORKFLOWS_DIR" 2>/dev/null || true
  echo
  
  echo "--- Conda Environments ---"
  if [[ -x "$CONDA_DIR/bin/conda" ]]; then
    "$CONDA_DIR/bin/conda" env list 2>/dev/null || true
  else
    echo "Miniconda not installed"
  fi
  echo
  
  echo "--- State File ---"
  if [[ -f "$STATE_FILE" ]]; then
    cat "$STATE_FILE"
  else
    echo "No state file"
  fi
  echo
}
