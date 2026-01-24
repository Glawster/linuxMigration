#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# llava install step (no DRY_RUN checks here)
# ============================================================

LLAVA_VERSION="${LLAVA_VERSION:-1.5}"
LLAVA_REF="${LLAVA_REF:-v1.5}"
LLAVA_DIR="${LLAVA_DIR:-/workspace/LLaVA}"
LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
CONDA_DIR="${CONDA_DIR:-/workspace/miniconda3}"

log "...installing llava"
log "......llava dir: $LLAVA_DIR"
log "......llava env: $LLAVA_ENV_NAME"
log "......llava version: $LLAVA_VERSION"
log "......llava ref: $LLAVA_REF"

# ------------------------------------------------------------
# ensure conda is available (do NOT reconfigure tos/channels)
# ------------------------------------------------------------
if ! ensureConda "$CONDA_DIR"; then
  die "conda not available"
fi

# ------------------------------------------------------------
# ensure llava conda environment
# ------------------------------------------------------------
if conda env list | awk '{print $1}' | grep -qx "$LLAVA_ENV_NAME"; then
  log "...conda env exists: $LLAVA_ENV_NAME"
else
  log "...creating conda environment: $LLAVA_ENV_NAME"
  run "conda create -y -n \"$LLAVA_ENV_NAME\" python=3.10"
fi

# shellcheck disable=SC1091
run "source \"$CONDA_DIR/etc/profile.d/conda.sh\" && conda activate \"$LLAVA_ENV_NAME\""

# ------------------------------------------------------------
# clone / update llava
# ------------------------------------------------------------
if [[ ! -d "$LLAVA_DIR/.git" ]]; then
  log "...cloning llava repository"
  run "git clone https://github.com/haotian-liu/LLaVA.git \"$LLAVA_DIR\""
else
  log "...updating llava repository"
  run "cd \"$LLAVA_DIR\" && git fetch --tags"
fi

log "...checking out llava ref: $LLAVA_REF"
run "cd \"$LLAVA_DIR\" && git checkout \"$LLAVA_REF\""
run "cd \"$LLAVA_DIR\" && git reset --hard \"$LLAVA_REF\""

# ------------------------------------------------------------
# install llava + deps
# ------------------------------------------------------------
log "...installing llava dependencies"
run "cd \"$LLAVA_DIR\" && pip install --root-user-action=ignore -r requirements.txt"

log "...installing llava (editable)"
run "cd \"$LLAVA_DIR\" && pip install --root-user-action=ignore -e ."

# ------------------------------------------------------------
# optional: write helper start script
# ------------------------------------------------------------
START_SCRIPT="/workspace/startLlavaApi.sh"

log "...writing llava start helper: $START_SCRIPT"
cat > "$START_SCRIPT" <<EOF
#!/usr/bin/env bash
set -e
source "$CONDA_DIR/etc/profile.d/conda.sh"
conda activate "$LLAVA_ENV_NAME"
echo "llava env active: \$(python -V)"
EOF

run "chmod +x \"$START_SCRIPT\""

markStepDone "LLAVA"

log "llava installed"
