#!/usr/bin/env bash
# steps/40_comfyui.sh
# Setup ComfyUI

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/git.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  log "==> step: comfyui"
  
  # Check if already done and not forcing
  if isStepDone "COMFYUI" && [[ "${FORCE:-0}" != "1" ]]; then
    log "...comfyui already configured (use --force to rerun)"
    return 0
  fi
  
  # Ensure repos
  ensureGitRepo "$COMFY_DIR" "https://github.com/comfyanonymous/ComfyUI.git"
  ensureGitRepo "$COMFY_DIR/custom_nodes/ComfyUI-Manager" "https://github.com/ltdrdata/ComfyUI-Manager.git"
  
  # Activate conda
  activateCondaEnv "$CONDA_DIR" "$ENV_NAME"
  
  # Install dependencies
  log "installing ComfyUI dependencies"
  
  local torch_index="${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"
  
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    echo "${DRY_PREFIX:-...[]} pip install --upgrade pip wheel"
    echo "${DRY_PREFIX:-...[]} pip install torch torchvision torchaudio --index-url $torch_index"
    echo "${DRY_PREFIX:-...[]} pip install -r $COMFY_DIR/requirements.txt"
    echo "${DRY_PREFIX:-...[]} pip install -r $COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"
  else
    python -m pip install --upgrade pip wheel
    pip install torch torchvision torchaudio --index-url "$torch_index"
    pip install -r "$COMFY_DIR/requirements.txt"
    
    # Install Manager dependencies if exists
    if [[ -f "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt" ]]; then
      pip install -r "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"
    fi
    
    # Verify CUDA
    python -c "import torch; print('cuda?', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"
  fi
  
  markStepDone "COMFYUI"
  log "...comfyui done"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
