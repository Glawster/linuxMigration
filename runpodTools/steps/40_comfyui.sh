#!/usr/bin/env bash
# steps/40_comfyui.sh
# Setup ComfyUI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/git.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  logTask "ComfyUI"

  # Check if already done and not forcing
  if isStepDone "COMFYUI" && [[ "${FORCE:-0}" != "1" ]]; then
    log "comfyui already configured (use --force to rerun)"
    return 0
  fi

  # Ensure repos (remote-safe via ensureGitRepo)
  ensureGitRepo "$COMFY_DIR" "https://github.com/comfyanonymous/ComfyUI.git"
  ensureGitRepo "$COMFY_DIR/custom_nodes/ComfyUI-Manager" "https://github.com/ltdrdata/ComfyUI-Manager.git"

  # the following don't seen to install so commented out
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"     # ComfyuiImactPack
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git"  # ComfyuiImactSubPack
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/facebookresearch/sam2"                # ComfyuiImactPack
  # ComfyUI Impact Subpack installed by pip

  # Install dependencies
  log "installing ComfyUI dependencies"

  local torch_index="${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"

  condaRunCmd "${ENV_NAME}" python --version
  condaRunCmd "${ENV_NAME}" python -m pip install --root-user-action=ignore --upgrade pip wheel

  log "installing comfyui requirements"
  condaRunCmd "$ENV_NAME" python -m pip install --root-user-action=ignore -r "$COMFY_DIR/requirements.txt"
  condaRunCmd "$ENV_NAME" python -m pip install --root-user-action=ignore -r "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"

  # Verify CUDA
  condaRunCmd "$ENV_NAME" python -c "import torch; print('cuda?', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"

  log "generating comfyStart.sh helper"

  local tmpFile
  tmpFile="$(mktemp)"

  generatecomfyStartScript "$tmpFile"

  runLocal scp "${SCP_OPTS[@]}" "$tmpFile" "${SSH_TARGET}:${WORKSPACE_ROOT}/comfyStart.sh"
  run "chmod +x ${WORKSPACE_ROOT}/comfyStart.sh"

  rm -f "$tmpFile"

  log "comfyStart.sh installed to /workspace"

  markStepDone "COMFYUI"
  log "comfyui done\n"
}

generatecomfyStartScript() {
  local outFile="$1"

  cat > "$outFile" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/workspace"
COMFY_DIR="$WORKSPACE/ComfyUI"
CONDA_DIR="$WORKSPACE/miniconda3"
CONDA_EXE="$CONDA_DIR/bin/conda"
ENV_NAME="runpod"
PORT=8188
SESSION="comfyui"

if ! command -v ss >/dev/null 2>&1; then
  echo "ERROR: ss not available; cannot check port usage" >&2
  exit 1
fi

if ss -ltn | awk '{print $4}' | grep -q ":${PORT}\$"; then
  echo "ERROR: port ${PORT} already in use"
  ss -ltnp | grep ":${PORT}" || true
  exit 1
fi

if [[ ! -d "$COMFY_DIR" ]]; then
  echo "ERROR: ComfyUI directory not found: $COMFY_DIR" >&2
  exit 1
fi

if [[ ! -x "$CONDA_EXE" ]]; then
  echo "ERROR: conda not found/executable at $CONDA_EXE" >&2
  exit 1
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not available; starting ComfyUI in foreground"
  exec "$CONDA_EXE" run -n "$ENV_NAME" --no-capture-output     bash -lc "cd '$COMFY_DIR' && python main.py --listen 0.0.0.0 --port '$PORT'"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "comfyui already running (tmux session: $SESSION)"
  exit 0
fi

LOG_DIR="$WORKSPACE/.runpod/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/comfyui.${PORT}.log"

tmux new-session -d -s "$SESSION" bash -lc   "'$CONDA_EXE' run -n '$ENV_NAME' --no-capture-output bash -lc "cd '$COMFY_DIR' && python main.py --listen 0.0.0.0 --port '$PORT'" 2>&1 | tee -a '$LOG_FILE'"

echo "comfyui started (tmux session: $SESSION)"
echo "log: $LOG_FILE"

EOF

  chmod +x "$outFile"
}


if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi