#!/usr/bin/env bash
set -euo pipefail

resolveLlavaRef() {
  local dir="$1"
  local desired="$2"

  # Fetch tags first
  runCmd git -C "$dir" fetch --tags --force

  # If exact ref exists, use it
  if runCmd git -C "$dir" rev-parse --verify -q "$desired" >/dev/null 2>&1; then
    echo "$desired"
    return 0
  fi

  # Try common alternatives
  local alt=""
  alt="$(runSh "git -C \"$dir\" tag -l \"v1.5*\" | sort -V | tail -n 1")"
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
LLAVA_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA}"
LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
CONDA_DIR="${CONDA_DIR:-${WORKSPACE_ROOT}/miniconda3}"

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

ensureGitRepo "$LLAVA_DIR" "https://github.com/haotian-liu/LLaVA.git" "llava"

LLAVA_REF="${LLAVA_REF:-v1.5}"

log "checking out llava ref: $LLAVA_REF"
resolvedRef="$(resolveLlavaRef "$LLAVA_DIR" "$LLAVA_REF")"
log "resolved llava ref: $resolvedRef"

runCmd git -C "$LLAVA_DIR" checkout "$resolvedRef"
runCmd git -C "$LLAVA_DIR" reset --hard "$resolvedRef"

#log "installing llava dependencies"
condaEnvCmd "$LLAVA_ENV_NAME" pip install --root-user-action=ignore 'protobuf<5' sentencepiece
if runSh test -f "$LLAVA_DIR/requirements.txt"; then
  condaEnvCmd "$LLAVA_ENV_NAME" pip install -r "$LLAVA_DIR/requirements.txt"
else
  log "skip (no requirements.txt)"
fi

#log "installing llava (editable)"
condaEnvCmd "$LLAVA_ENV_NAME" pip install -e "$LLAVA_DIR"
condaEnvCmd "$LLAVA_ENV_NAME" python -c 'import llava; print(llava.__file__)'

# ------------------------------------------------------------
# optional: write helper start script
# ------------------------------------------------------------

START_SCRIPT="llavaStart.sh"

log "writing llava start helper: $START_SCRIPT"
cat > "$START_SCRIPT" <<EOF
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE_ROOT}"
LLAVA_DIR="\${LLAVA_DIR:-\$WORKSPACE/LLaVA}"
CONDA_DIR="\$WORKSPACE/miniconda3"
CONDA_EXE="\$CONDA_DIR/bin/conda"
ENV_NAME="${LLAVA_ENV_NAME}"

# You MUST set this to a real model path or HF repo id.
# Examples:
#   export LLAVA_MODEL_PATH=/workspace/models/llava-1.5-7b
#   export LLAVA_MODEL_PATH=liuhaotian/llava-v1.5-7b
LLAVA_MODEL_PATH="\${LLAVA_MODEL_PATH:-}"

# Ports: use safe internal range (avoid nginx / runpod reserved ports like 3001/9091)
CONTROLLER_PORT="\${LLAVA_CONTROLLER_PORT:-7001}"
WORKER_PORT="\${LLAVA_WORKER_PORT:-7002}"
WEB_PORT="\${LLAVA_WEB_PORT:-7003}"

SESSION_CONTROLLER="\${LLAVA_SESSION_CONTROLLER:-llava_controller}"
SESSION_WORKER="\${LLAVA_SESSION_WORKER:-llava_worker}"
SESSION_WEB="\${LLAVA_SESSION_WEB:-llava_web}"

LOG_DIR="\$WORKSPACE/.runpod/logs"
mkdir -p "\$LOG_DIR"
LOG_CONTROLLER="\$LOG_DIR/llava.controller.\${CONTROLLER_PORT}.log"
LOG_WORKER="\$LOG_DIR/llava.worker.\${WORKER_PORT}.log"
LOG_WEB="\$LOG_DIR/llava.web.\${WEB_PORT}.log"

requireCmd() {
  local c="\$1"
  command -v "\$c" >/dev/null 2>&1 || { echo "ERROR: missing command: \$c" >&2; exit 1; }
}

portInUse() {
  local p="\$1"
  ss -ltn | awk '{print \$4}' | grep -q ":\${p}\$"
}

assertPortFree() {
  local p="\$1"
  if portInUse "\$p"; then
    echo "ERROR: port \$p already in use" >&2
    ss -ltnp | grep ":\${p}" || true
    exit 1
  fi
}

# --- sanity ---
requireCmd ss
requireCmd tmux

[[ -d "\$LLAVA_DIR" ]] || { echo "ERROR: llava directory not found: \$LLAVA_DIR" >&2; exit 1; }
[[ -x "\$CONDA_EXE" ]] || { echo "ERROR: conda not found/executable at \$CONDA_EXE" >&2; exit 1; }

if [[ -z "\$LLAVA_MODEL_PATH" ]]; then
  echo "ERROR: LLAVA_MODEL_PATH is not set (required to start model worker)" >&2
  echo "Set it to a local path or HF repo id, e.g.:" >&2
  echo "  export LLAVA_MODEL_PATH=/workspace/models/llava-1.5-7b" >&2
  echo "  export LLAVA_MODEL_PATH=liuhaotian/llava-v1.5-7b" >&2
  exit 1
fi

# ensure chosen ports are free
assertPortFree "\$CONTROLLER_PORT"
assertPortFree "\$WORKER_PORT"
assertPortFree "\$WEB_PORT"

# --- controller ---
if tmux has-session -t "\$SESSION_CONTROLLER" 2>/dev/null; then
  echo "controller already running (tmux session: \$SESSION_CONTROLLER)"
else
  tmux new-session -d -s "\$SESSION_CONTROLLER" \\
    "bash -lc 'set -euo pipefail; cd \"\$LLAVA_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output \\
      python -m llava.serve.controller --host 0.0.0.0 --port \"\$CONTROLLER_PORT\" \\
      2>&1 | tee -a \"\$LOG_CONTROLLER\"'"
  echo "controller started: session=\$SESSION_CONTROLLER port=\$CONTROLLER_PORT log=\$LOG_CONTROLLER"
fi

# --- worker ---
if tmux has-session -t "\$SESSION_WORKER" 2>/dev/null; then
  echo "worker already running (tmux session: \$SESSION_WORKER)"
else
  tmux new-session -d -s "\$SESSION_WORKER" \\
    "bash -lc 'set -euo pipefail; cd \"\$LLAVA_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output \\
      python -m llava.serve.model_worker \\
        --host 0.0.0.0 \\
        --port \"\$WORKER_PORT\" \\
        --controller http://127.0.0.1:\${CONTROLLER_PORT} \\
        --model-path \"\$LLAVA_MODEL_PATH\" \\
      2>&1 | tee -a \"\$LOG_WORKER\"'"
  echo "worker started: session=\$SESSION_WORKER port=\$WORKER_PORT log=\$LOG_WORKER"
fi

# --- web (optional but useful) ---
if tmux has-session -t "\$SESSION_WEB" 2>/dev/null; then
  echo "web already running (tmux session: \$SESSION_WEB)"
else
  tmux new-session -d -s "\$SESSION_WEB" \\
    "bash -lc 'set -euo pipefail; cd \"\$LLAVA_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output \\
      python -m llava.serve.gradio_web_server \\
        --host 0.0.0.0 \\
        --port \"\$WEB_PORT\" \\
        --controller http://127.0.0.1:\${CONTROLLER_PORT} \\
      2>&1 | tee -a \"\$LOG_WEB\"'"
  echo "web started: session=\$SESSION_WEB port=\$WEB_PORT log=\$LOG_WEB"
fi

echo "llava stack running:"
echo "  controller: http://127.0.0.1:\$CONTROLLER_PORT  (tmux: \$SESSION_CONTROLLER)"
echo "  worker     : http://127.0.0.1:\$WORKER_PORT      (tmux: \$SESSION_WORKER)"
echo "  web ui     : http://127.0.0.1:\$WEB_PORT         (tmux: \$SESSION_WEB)"
EOF

chmod +x "$START_SCRIPT"

runHostCmd scp "${SCP_OPTS[@]}" "$START_SCRIPT" "${SSH_TARGET}:${WORKSPACE_ROOT}/llavaStart.sh"
runSh "chmod +x \"${WORKSPACE_ROOT}/llavaStart.sh\""

markStepDone "LLAVA"

log "llava installed"
