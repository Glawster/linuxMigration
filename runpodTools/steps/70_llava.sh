#!/usr/bin/env bash
# steps/70_llava.sh
# Install LLaVA (v1.5 / v1.6) in a dedicated conda environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"

# ------------------------------------------------------------
# Config (override via env)
# ------------------------------------------------------------
LLAVA_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA}"
LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"

# Prefer a simple selector: 1.6 or 1.5
LLAVA_VERSION="${LLAVA_VERSION:-1.6}"

# If you know the exact ref/tag/commit you want, set LLAVA_REF.
# Otherwise we attempt "v<LLAVA_VERSION>" and fall back to "main".
LLAVA_REF="${LLAVA_REF:-v${LLAVA_VERSION}}"

main() {
  if isStepDone "LLAVA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "llava already installed (use --force to rerun)"
    return 0
  fi

  log "installing llava"
  log "...llava dir: ${LLAVA_DIR}"
  log "...llava env: ${LLAVA_ENV_NAME}"
  log "...llava version: ${LLAVA_VERSION}"
  log "...llava ref: ${LLAVA_REF}"

  # Ensure conda + env exist
  if ! ensureConda "$CONDA_DIR"; then
    die "conda not available"
  fi

  if ! acceptCondaTos "$CONDA_DIR"; then
    die "conda tos accept failed"
  fi

  if ! ensureCondaChannels "$CONDA_DIR"; then
    die "conda channel configuration failed"
  fi

  # LLaVA generally works well on python 3.10
  if ! ensureCondaEnv "$CONDA_DIR" "$LLAVA_ENV_NAME" "3.10"; then
    die "conda env setup failed"
  fi

  # Clone / update repo
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "mkdir -p '${LLAVA_DIR}'"
    dryrun "git clone https://github.com/haotian-liu/LLaVA '${LLAVA_DIR}'"
  else
    run bash -lc "mkdir -p '$(dirname "$LLAVA_DIR")'"
    if run bash -lc "test -d '${LLAVA_DIR}/.git'"; then
      log "...repo exists, updating"
      run bash -lc "cd '${LLAVA_DIR}' && git fetch --all --tags --prune"
    else
      log "...cloning repo"
      run bash -lc "git clone https://github.com/haotian-liu/LLaVA '${LLAVA_DIR}'"
    fi

    # Try checkout the requested ref, fall back safely
    if ! run bash -lc "cd '${LLAVA_DIR}' && git checkout '${LLAVA_REF}'"; then
      warn "llava ref not found: ${LLAVA_REF}"
      warn "...falling back to main"
      run bash -lc "cd '${LLAVA_DIR}' && git checkout main"
    fi
  fi

  # Install python deps (in llava env)
  log "...installing python dependencies"
  run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${LLAVA_ENV_NAME}' && python -V"

  # NOTE: we deliberately do NOT force-install torch here, because RunPod base images vary.
  # If torch isn't present (or is CPU-only), we'll detect and warn.
  run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${LLAVA_ENV_NAME}' && pip install -U pip setuptools wheel"

  # Install repo requirements if present
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "pip install -r '${LLAVA_DIR}/requirements.txt'"
    dryrun "pip install -e '${LLAVA_DIR}'"
    dryrun "pip install fastapi 'uvicorn[standard]'"
  else
    run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${LLAVA_ENV_NAME}' && \
      if test -f '${LLAVA_DIR}/requirements.txt'; then pip install -r '${LLAVA_DIR}/requirements.txt'; fi"

    # Editable install of llava
    run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${LLAVA_ENV_NAME}' && pip install -e '${LLAVA_DIR}'"

    # FastAPI runtime (for your local vision api service)
    run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${LLAVA_ENV_NAME}' && pip install fastapi 'uvicorn[standard]'"
  fi

  # Basic sanity checks
  log "...sanity checks"
  run bash -lc "source '${CONDA_DIR}/etc/profile.d/conda.sh' && conda activate '${LLAVA_ENV_NAME}' && python - <<'PY'
import sys
print('python:', sys.version.split()[0])
try:
  import torch
  print('torch:', torch.__version__, 'cuda:', torch.cuda.is_available())
except Exception as e:
  print('torch: not importable:', e)
try:
  import transformers
  print('transformers:', transformers.__version__)
except Exception as e:
  print('transformers: not importable:', e)
PY"

  # Drop a helper start script for later (doesn't run anything yet)
  log "...writing /workspace/startLlavaApi.sh"
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "write /workspace/startLlavaApi.sh"
  else
    run bash -lc "cat > '${WORKSPACE_ROOT}/startLlavaApi.sh' <<'SH'
#!/usr/bin/env bash
set -euo pipefail

CONDA_DIR=\"${CONDA_DIR}\"
ENV_NAME=\"${LLAVA_ENV_NAME}\"

# You will add your FastAPI server entrypoint later.
# For now this just confirms the environment activates correctly.

source \"${CONDA_DIR}/etc/profile.d/conda.sh\"
conda activate \"${LLAVA_ENV_NAME}\"

python -c \"import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())\"
echo 'llava env ready. add your api server and start it here.'
SH
chmod +x '${WORKSPACE_ROOT}/startLlavaApi.sh'"
  fi

  markStepDone "LLAVA"
  log "llava installed"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
