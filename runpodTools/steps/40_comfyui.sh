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
  ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/ltdrdata/ComfyUI-Impact-Pack.git"     # ComfyuiImactPack
  ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/ltdrdata/ComfyUI-Impact-Subpack.git"  # ComfyuiImactSubPack
  #ensureGitRepo "$COMFY_DIR/custom_nodes" "https://github.com/facebookresearch/sam2"                # ComfyuiImactPack
  # ComfyUI Impact Subpack installed by pip

  # Install dependencies
  log "installing ComfyUI dependencies"

  local torch_index="${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"

  condaEnvRun "$ENV_NAME" python --version
  condaEnvRun "$ENV_NAME" python -m pip install --root-user-action=ignore --upgrade pip wheel
  condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore torch torchvision torchaudio "ultralytics>=8.3.162" --index-url "$torch_index"

  # Combine requirements files for single pip install (more efficient)
  local req_args=(-r "$COMFY_DIR/requirements.txt")

  # IMPORTANT: requirements file check must be REMOTE
  if run test -f "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"; then
    req_args+=(-r "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt")
  fi

  condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore "${req_args[@]}"

  # Verify CUDA
  condaEnvRun "$ENV_NAME" python -c "import torch; print('cuda?', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"

  log "generating startComfyUI.sh helper"

  local tmpFile
  tmpFile="$(mktemp)"

  generateStartComfyUiScript "$tmpFile"

  runLocal scp "${SSH_OPTS[@]}" "$tmpFile" "${SSH_TARGET}:/workspace/startComfyUI.sh"
  run bash -lc "chmod +x /workspace/startComfyUI.sh"

  rm -f "$tmpFile"

  log "startComfyUI.sh installed to /workspace"

  markStepDone "COMFYUI"
  log "...comfyui done"
}

generateStartComfyUiScript() {
  local outFile="$1"

  cat > "$outFile" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/workspace"
COMFY_DIR="$WORKSPACE/ComfyUI"
CONDA_DIR="$WORKSPACE/miniconda3"
ENV_NAME="runpod"
PORT=8188
SESSION="comfyui"

if [[ ! -d "$COMFY_DIR" ]]; then
  echo "ERROR: ComfyUI directory not found: $COMFY_DIR" >&2
  exit 1
fi

if [[ ! -f "$CONDA_DIR/etc/profile.d/conda.sh" ]]; then
  echo "ERROR: conda not found at $CONDA_DIR" >&2
  exit 1
fi

source "$CONDA_DIR/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

cd "$COMFY_DIR"

if command -v tmux >/dev/null 2>&1; then
  if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "ComfyUI already running (tmux session: $SESSION)"
  else
    tmux new-session -d -s "$SESSION" \
      "python main.py --listen 0.0.0.0 --port $PORT"
    echo "Started ComfyUI in tmux session '$SESSION' on port $PORT"
  fi
else
  echo "tmux not available; starting ComfyUI in foreground"
  exec python main.py --listen 0.0.0.0 --port $PORT
fi
EOF

  chmod +x "$outFile"
}


if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi