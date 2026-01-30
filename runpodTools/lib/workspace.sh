#!/usr/bin/env bash
# lib/workspace.sh
# Common workspace paths and inventory helpers

# ============================================================
# Workspace paths
# ============================================================

: "${WORKSPACE_ROOT:?WORKSPACE_ROOT must be set by bootstrap}"

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

ensureStateDir() {
  runCmd mkdir -p "$(dirname "$STATE_FILE")"
}

# ------------------------------------------------------------
# isStepDone (REMOTE)
# ------------------------------------------------------------
isStepDone() {
  local step="$1"

  runSh "test -f '${STATE_FILE}' || exit 1; \
    source '${STATE_FILE}'; \
    var='DONE_${step}'; \
    [[ \"\${!var:-0}\" == '1' ]]"
}

# ------------------------------------------------------------
# markStepDone (REMOTE)
# ------------------------------------------------------------

markStepDone() {
  local step="$1"
  ensureStateDir || true

  local step_q state_q
  step_q=$(printf '%q' "$step")
  state_q=$(printf '%q' "$STATE_FILE")

  runSh "$(cat <<EOF
STEP=${step_q}
STATE_FILE=${state_q}

if test -f "\$STATE_FILE"; then
  if grep -q "^DONE_\${STEP}=" "\$STATE_FILE"; then
    sed -i "s/^DONE_\${STEP}=.*/DONE_\${STEP}=1/" "\$STATE_FILE"
  else
    printf '%s\n' "DONE_\${STEP}=1" >> "\$STATE_FILE"
  fi
else
  printf '%s\n' "DONE_\${STEP}=1" > "\$STATE_FILE"
fi
EOF
)"
}


# ------------------------------------------------------------
# showInventory (REMOTE)
# ------------------------------------------------------------

showInventory() {
  log "workspace inventory"

  runSh "$(cat <<'EOF'
echo "--- Directories ---"
ls -ld \
  "'${WORKSPACE_ROOT}'" \
  "'${RUNPOD_DIR}'" \
  "'${CONDA_DIR}'" \
  "'${COMFY_DIR}'" \
  "'${KOHYA_DIR}'" \
  "'${WORKFLOWS_DIR}'" \
  2>/dev/null || true

echo "--- Conda Environments ---"
if test -x "'${CONDA_DIR}'/condabin/conda"; then
  "'${CONDA_DIR}'/condabin/conda" env list 2>/dev/null || true
elif test -x "'${CONDA_DIR}'/bin/conda"; then
  "'${CONDA_DIR}'/bin/conda" env list 2>/dev/null || true
else
  echo "Miniconda not installed"
fi

echo "--- State File ---"
if test -f "'${STATE_FILE}'"; then
  cat "'${STATE_FILE}'"
else
  echo "No state file"
fi
EOF
  )" 
}