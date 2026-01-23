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

  # Install dependencies
  log "installing ComfyUI dependencies"

  local torch_index="${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"

  condaEnvRun "$ENV_NAME" python --version
  condaEnvRun "$ENV_NAME" python -m pip install --root-user-action=ignore --upgrade pip wheel
  condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore torch torchvision torchaudio --index-url "$torch_index"

  # Combine requirements files for single pip install (more efficient)
  local req_args=(-r "$COMFY_DIR/requirements.txt")

  # IMPORTANT: requirements file check must be REMOTE
  if run test -f "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"; then
    req_args+=(-r "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt")
  fi

  condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore "${req_args[@]}"

  # Verify CUDA
  condaEnvRun "$ENV_NAME" python -c "import torch; print('cuda?', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"

  markStepDone "COMFYUI"
  log "...comfyui done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
