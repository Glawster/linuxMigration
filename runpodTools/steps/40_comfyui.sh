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

  # Check if already done and not forcing
  if isStepDone "COMFYUI" && [[ "${FORCE:-0}" != "1" ]]; then
    log "comfyui already configured (use --force to rerun)"
    return 0
  fi

  # Ensure repos (remote-safe via ensureGitRepo)
  if ! isStepDone "COMFYUI_REPO"; then
    log "ensuring comfyui git repository"
    ensureGitRepo "$COMFY_DIR" "https://github.com/comfyanonymous/ComfyUI.git" "ComfyUI"
    markStepDone "COMFYUI_REPO"
  else
    log "comfyui repository already cloned"
  fi

  if ! isStepDone "COMFYUI_MANAGER"; then
    log "ensuring comfyui-manager custom node"
    ensureGitRepo "$COMFY_DIR/custom_nodes/ComfyUI-Manager" "https://github.com/ltdrdata/ComfyUI-Manager.git" "ComfyUI-Manager"
    markStepDone "COMFYUI_MANAGER"
  else
    log "comfyui-manager already cloned"
  fi

  # the following don't seen to install so commented out
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"     "ComfyuiImactPack"
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git"  "ComfyuiImactSubPack"
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/facebookresearch/sam2"                "ComfyuiImactPack"
  # ComfyUI Impact Subpack installed by pip

  # Upgrade pip and wheel
  if ! isStepDone "COMFYUI_PIP_UPGRADE"; then
    log "upgrading pip and wheel"
    local torch_index="${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"
    condaEnvCmd "${ENV_NAME}" python --version
    condaEnvCmd "${ENV_NAME}" python -m pip install --root-user-action=ignore --upgrade pip wheel
    markStepDone "COMFYUI_PIP_UPGRADE"
  else
    log "pip and wheel already upgraded"
  fi

  # Install ComfyUI requirements
  if ! isStepDone "COMFYUI_REQUIREMENTS"; then
    log "installing comfyui requirements"
    condaEnvCmd "$ENV_NAME" python -m pip install --root-user-action=ignore -r "$COMFY_DIR/requirements.txt"
    markStepDone "COMFYUI_REQUIREMENTS"
  else
    log "comfyui requirements already installed"
  fi

  # Install ComfyUI-Manager requirements
  if ! isStepDone "COMFYUI_MANAGER_REQUIREMENTS"; then
    log "installing comfyui-manager requirements"
    condaEnvCmd "$ENV_NAME" python -m pip install --root-user-action=ignore -r "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"
    markStepDone "COMFYUI_MANAGER_REQUIREMENTS"
  else
    log "comfyui-manager requirements already installed"
  fi

  # Verify CUDA (always run as quick verification)
  if ! isStepDone "COMFYUI_CUDA_CHECK"; then
    log "verifying CUDA availability"
    condaEnvCmd "$ENV_NAME" python -c "import torch; print('cuda?', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
    markStepDone "COMFYUI_CUDA_CHECK"
  else
    log "cuda already verified"
  fi

  # Generate and upload comfyStart.sh (always regenerate for potential updates)
  log "generating comfyStart.sh helper"

  START_SCRIPT="comfyStart.sh"

  generateScript "$START_SCRIPT"

  runHostCmd scp "${SCP_OPTS[@]}" "$START_SCRIPT" "${SSH_TARGET}:${WORKSPACE_ROOT}/comfyStart.sh"
  runSh "chmod +x ${WORKSPACE_ROOT}/comfyStart.sh"

  log "comfyStart.sh installed to /workspace"

  markStepDone "COMFYUI"
  log "comfyui done\n"
}

generateScript() {
  local outFile="$1"

  cat > "$outFile" <<EOF
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE_ROOT:-/workspace}"
COMFY_DIR="\$WORKSPACE/ComfyUI"
CONDA_DIR="\$WORKSPACE/miniconda3"
CONDA_EXE="\$CONDA_DIR/bin/conda"
ENV_NAME="${ENV_NAME:-runpod}"
PORT="${COMFYUI_PORT:-8188}"
SESSION="comfyui"

# optional defaults used by llava/adapter (exported for convenience)
export LLAVA_MODEL_PATH="${LLAVA_MODEL_PATH:-liuhaotian/llava-v1.5-7b}"
export LLAVA_GRADIO_URL="${LLAVA_GRADIO_URL:-http://127.0.0.1:7003}"
export LLAVA_API_NAME="${LLAVA_API_NAME:-/add_text_1}"
export LAVA_GRADIO_URL="${LAVA_GRADIO_URL:-$LLAVA_GRADIO_URL}"
export LAVA_API_NAME="${LAVA_API_NAME:-$LLAVA_API_NAME}"

if ! command -v ss >/dev/null 2>&1; then
  echo "ERROR: ss not available; cannot check port usage" >&2
  exit 1
fi

if ss -ltn | awk '{print \$4}' | grep -q ":\${PORT}\$"; then
  echo "ERROR: port \${PORT} already in use"
  ss -ltnp | grep ":\${PORT}" || true
  exit 1
fi

if [[ ! -d "\$COMFY_DIR" ]]; then
  echo "ERROR: ComfyUI directory not found: \$COMFY_DIR" >&2
  exit 1
fi

if [[ ! -x "\$CONDA_EXE" ]]; then
  echo "ERROR: conda not found/executable at \$CONDA_EXE" >&2
  exit 1
fi

LOG_DIR="\$WORKSPACE/logs"
mkdir -p "\$LOG_DIR"
LOG_FILE="\$LOG_DIR/comfyui.\${PORT}.log"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not available; starting ComfyUI in foreground"
  exec "\$CONDA_EXE" run -n "\$ENV_NAME" --no-capture-output \\
    bash -lc "cd '\$COMFY_DIR' && python main.py --listen 0.0.0.0 --port '\$PORT'" \\
    2>&1 | tee -a "\$LOG_FILE"
fi

if tmux has-session -t "\$SESSION" 2>/dev/null; then
  echo "comfyui already running (tmux session: \$SESSION)"
  echo "log: \$LOG_FILE"
  exit 0
fi

tmux new-session -d -s "\$SESSION" \\
  "bash -lc 'set -euo pipefail; cd \"\$COMFY_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output python main.py --listen 0.0.0.0 --port \"\$PORT\" 2>&1 | tee -a \"\$LOG_FILE\"'"

echo "comfyui started (tmux session: \$SESSION)"
echo "log: \$LOG_FILE"
EOF

  chmod +x "$outFile"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi