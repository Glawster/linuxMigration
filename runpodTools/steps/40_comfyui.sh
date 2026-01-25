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

  condaEnvRun "$ENV_NAME" python --version
  condaEnvRun "$ENV_NAME" python -m pip install --root-user-action=ignore --upgrade pip wheel
  condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore torch torchvision torchaudio --index-url "$torch_index"

  # ------------------------------------------------------------
  # comfyui requirements install (remote-aware, hash-gated)
  # ------------------------------------------------------------

  local hashFile="/workspace/.runpod/reqhash.comfyui"
  local remoteReqFiles=(
    "$COMFY_DIR/requirements.txt"
    "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"
  )

  # Build the actual list of existing req files on REMOTE
  local reqFiles=()
  for f in "${remoteReqFiles[@]}"; do
    if run test -f "$f"; then
      reqFiles+=("$f")
    fi
  done

  # Safety: at least the base requirements must exist
  if (( ${#reqFiles[@]} == 0 )); then
    die "no requirements files found under $COMFY_DIR"
  fi

  # Compute hash on REMOTE from file contents (not filenames)
  # This avoids local/remote mismatch and handles multiple files correctly.
  currentHash="$(run sh -lc "cat ${reqFiles[*]} | sha256sum | awk '{print \$1}'")"

  # Read previous hash from REMOTE marker file (empty if missing)
  lastHash="$(run sh -lc "cat \"$hashFile\" 2>/dev/null || true")"

  if [[ "$currentHash" == "$lastHash" && "${FORCE:-0}" != "1" ]]; then
    log "...comfyui requirements unchanged; skipping pip install"
  else
    log "...comfyui requirements changed; installing dependencies"
    # Note: condaEnvRun should already be remote-aware in your framework
    condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore -r "${reqFiles[0]}"

    # If you have more than one requirements file, install them all explicitly:
    # (pip doesn't accept multiple -r in a single -r; you add multiple -r flags)
    if (( ${#reqFiles[@]} > 1 )); then
      local pipArgs=()
      for rf in "${reqFiles[@]}"; do
        pipArgs+=("-r" "$rf")
      done
      condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore "${pipArgs[@]}"
    else
      condaEnvRun "$ENV_NAME" pip install --root-user-action=ignore -r "${reqFiles[0]}"
    fi

    # Persist marker on REMOTE
    run sh -lc "mkdir -p \"$(dirname "$hashFile")\" && echo \"$currentHash\" > \"$hashFile\""
  fi


  # Verify CUDA
  condaEnvRun "$ENV_NAME" python -c "import torch; print('cuda?', torch.cuda.is_available()); print('gpu:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)"

  log "generating startComfyUI.sh helper"

  local tmpFile
  tmpFile="$(mktemp)"

  generateStartComfyUiScript "$tmpFile"

  runLocal scp "${SCP_OPTS[@]}" "$tmpFile" "${SSH_TARGET}:/workspace/startComfyUI.sh"
  run bash -lc "chmod +x /workspace/startComfyUI.sh"

  rm -f "$tmpFile"

  log "startComfyUI.sh installed to /workspace"

  markStepDone "COMFYUI"
  log "comfyui done\n"
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