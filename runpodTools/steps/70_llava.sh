#!/usr/bin/env bash
set -euo pipefail

resolveLlavaRef() {
  local dir="$1"
  local desired="$2"

  # Fetch tags first
  run git -C "$dir" fetch --tags --force

  # If exact ref exists, use it
  if run git -C "$dir" rev-parse --verify -q "$desired" >/dev/null 2>&1; then
    echo "$desired"
    return 0
  fi

  # Try common alternatives
  local alt=""
  alt="$(run bash -lc "git -C \"$dir\" tag -l \"v1.5*\" | sort -V | tail -n 1")"
  if [[ -n "$alt" ]]; then
    echo "$alt"
    return 0
  fi

  # Fallback: main
  echo "main"
}

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

# ============================================================
# llava install step (no DRY_RUN checks here)
# ============================================================

LLAVA_VERSION="${LLAVA_VERSION:-1.5}"
LLAVA_REF="${LLAVA_REF:-v1.5}"
LLAVA_DIR="${LLAVA_DIR:-/workspace/LLaVA}"
LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
CONDA_DIR="${CONDA_DIR:-/workspace/miniconda3}"

logTask "installing llava"

log "llava dir: $LLAVA_DIR"
log "llava env: $LLAVA_ENV_NAME"
log "llava version: $LLAVA_VERSION"
log "llava ref: $LLAVA_REF"

# ensure conda is available (do NOT reconfigure tos/channels)
if ! ensureConda ; then
  die "conda not available"
fi

# ensure llava conda environment
ensureCondaEnv "$LLAVA_ENV_NAME" "3.10"

ensureGitRepo "$LLAVA_DIR" "https://github.com/haotian-liu/LLaVA.git"

LLAVA_REF="${LLAVA_REF:-v1.5}"

log "checking out llava ref: $LLAVA_REF"
resolvedRef="$(resolveLlavaRef "$LLAVA_DIR" "$LLAVA_REF")"
log "resolved llava ref: $resolvedRef"

run git -C "$LLAVA_DIR" checkout "$resolvedRef"
run git -C "$LLAVA_DIR" reset --hard "$resolvedRef"

#log "installing llava dependencies"
condaEnvRun "$LLAVA_ENV_NAME" pip install --root-user-action=ignore 'protobuf<5' sentencepiece
if run test -f "$LLAVA_DIR/requirements.txt"; then
  condaEnvRun "$LLAVA_ENV_NAME" pip install -r "$LLAVA_DIR/requirements.txt"
else
  log "skip (no requirements.txt)"
fi

#log "installing llava (editable)"
condaEnvRun "$LLAVA_ENV_NAME" pip install -e "$LLAVA_DIR"
condaEnvRun "$LLAVA_ENV_NAME" python -c 'import llava; print(llava.__file__)'

# ------------------------------------------------------------
# optional: write helper start script
# ------------------------------------------------------------
START_SCRIPT="llavaStart.sh"

log "writing llava start helper: $START_SCRIPT"
cat > "$START_SCRIPT" <<EOF
#!/usr/bin/env bash
set -e
source "$CONDA_DIR/etc/profile.d/conda.sh"
conda activate "$LLAVA_ENV_NAME"
echo "llava env active: \$(python -V)"
EOF

runLocal scp "${SCP_OPTS[@]}" "$START_SCRIPT" "${SSH_TARGET}:/workspace/llavaStart.sh"
run bash -lc "chmod +x /workspace/$START_SCRIPT"

markStepDone "LLAVA"

log "llava installed"
