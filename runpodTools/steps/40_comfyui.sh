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


  local hashFile="/workspace/.runpod/reqhash.comfyui.${ENV_NAME}"
  local remoteReqFiles=(
    "$COMFY_DIR/requirements.txt"
    "$COMFY_DIR/custom_nodes/ComfyUI-Manager/requirements.txt"
  )

  local reqFiles=()
  for f in "${remoteReqFiles[@]}"; do
    if run test -f "$f"; then
      reqFiles+=("$f")
    fi
  done

  if (( ${#reqFiles[@]} == 0 )); then
    die "no requirements files found under $COMFY_DIR"
  fi

  # include python version so a recreated env doesn't incorrectly skip
  local pyver
  pyver="$(condaEnvRun "$ENV_NAME" python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")"

  currentHash="$(run sh -lc "echo 'py=${pyver}'; cat ${reqFiles[*]} | sha256sum | awk '{print \$1}'")"
  lastHash="$(run sh -lc "cat \"$hashFile\" 2>/dev/null || true")"

  needsInstall=0
  if [[ "$currentHash" != "$lastHash" || "${FORCE:-0}" == "1" ]]; then
    needsInstall=1
  else
    # sanity check: marker may exist but env may be missing deps
    if ! condaEnvRun "$ENV_NAME" python -c "import sqlalchemy" >/dev/null 2>&1; then
      warn "sqlalchemy missing despite hash marker; forcing reinstall"
      needsInstall=1
    fi
    if ! condaEnvRun "$ENV_NAME" python -c "import git" >/dev/null 2>&1; then
      warn "GitPython missing despite hash marker; forcing reinstall"
      needsInstall=1
    fi
  fi

  if [[ "$needsInstall" == "0" ]]; then
    log "...comfyui requirements unchanged and key imports present; skipping pip install"
  else
    log "...installing comfyui requirements"

    # ensure pip exists in the env and python -m pip works
    condaEnvRun "$ENV_NAME" python -m ensurepip --upgrade || true
    condaEnvRun "$ENV_NAME" python -m pip install --root-user-action=ignore --upgrade pip wheel

    local pipArgs=()
    for rf in "${reqFiles[@]}"; do
      pipArgs+=("-r" "$rf")
    done

    condaEnvRun "$ENV_NAME" python -m pip install --root-user-action=ignore "${pipArgs[@]}"

    # Manager needs GitPython (imports as "git")
    condaEnvRun "$ENV_NAME" python -m pip install --root-user-action=ignore --upgrade GitPython

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

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "comfyui already running (tmux session: $SESSION)"
  exit 0
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
    LOG_DIR="$WORKSPACE/.runpod/logs"
    mkdir -p "$LOG_DIR"
    LOG_FILE="$LOG_DIR/comfyui.${PORT}.log"

    tmux new-session -d -s "$SESSION" bash -lc \
      "source '$CONDA_DIR/etc/profile.d/conda.sh' \
      && conda activate '$ENV_NAME' \
      && cd '$COMFY_DIR' \
      && python main.py --listen 0.0.0.0 --port '$PORT' 2>&1 | tee -a '$LOG_FILE'"
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