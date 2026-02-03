#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# 70_llava (REMOTE setup via runSh/condaEnvCmd, LOCAL script gen via generateScript + scp)
# ------------------------------------------------------------

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
# shellcheck disable=SC1091
source "$LIB_DIR/run.sh"

# ------------------------------------------------------------
# helper: resolve a ref/tag/branch (REMOTE)
# ------------------------------------------------------------
resolveLlavaRef() {
  local dir="$1"
  local desired="$2"

  runSh "git -C \"$dir\" fetch --tags --force"

  if runSh "git -C \"$dir\" rev-parse --verify -q \"$desired\" >/dev/null 2>&1"; then
    echo "$desired"
    return 0
  fi

  local alt=""
  alt="$(runSh "git -C \"$dir\" tag -l \"v1.5*\" | sort -V | tail -n 1")"
  if [[ -n "$alt" ]]; then
    echo "$alt"
    return 0
  fi

  echo "main"
}

# ------------------------------------------------------------
# helper: generate llavaStart.sh LOCALLY (self-contained on pod)
# ------------------------------------------------------------
generateScript() {
  local outFile="$1"

  # bake in what we want self-contained on the pod
  local bakedWorkspaceRoot="${WORKSPACE_ROOT:-/workspace}"
  local bakedEnvName="${LLAVA_ENV_NAME:-llava}"

  cat >"$outFile" <<EOF
#!/usr/bin/env bash
set -euo pipefail

# baked-in defaults from bootstrap
WORKSPACE='${bakedWorkspaceRoot}'
ENV_NAME='${bakedEnvName}'

# runtime-overridable variables
LLAVA_DIR="\${LLAVA_DIR:-\${WORKSPACE}/LLaVA}"
CONDA_DIR="\${CONDA_DIR:-\${WORKSPACE}/miniconda3}"
CONDA_EXE="\${CONDA_EXE:-\${CONDA_DIR}/bin/conda}"

CONTROLLER_PORT="\${CONTROLLER_PORT:-7001}"
WORKER_PORT="\${WORKER_PORT:-7002}"
WEB_PORT="\${WEB_PORT:-7003}"

SESSION_CONTROLLER="\${SESSION_CONTROLLER:-controller}"
SESSION_WORKER="\${SESSION_WORKER:-worker}"
SESSION_WEB="\${SESSION_WEB:-web}"

requireCmd() {
  local c="\$1"
  command -v "\$c" >/dev/null 2>&1 || { echo "ERROR: required command not found: \$c" >&2; exit 1; }
}

portInUse() {
  local p="\$1"
  ss -ltn | awk '{print \$4}' | grep -q ":\${p}\$"
}

assertPortFree() {
  local p="\$1"
  if portInUse "\$p"; then
    echo "ERROR: port already in use: \$p" >&2
    exit 1
  fi
}

# --- sanity ---
requireCmd ss
requireCmd tmux

[[ -d "\$LLAVA_DIR" ]] || { echo "ERROR: llava directory not found: \$LLAVA_DIR" >&2; exit 1; }
[[ -x "\$CONDA_EXE" ]] || { echo "ERROR: conda not found/executable at \$CONDA_EXE" >&2; exit 1; }

LLAVA_MODEL_PATH="\${LLAVA_MODEL_PATH:-liuhaotian/llava-v1.5-7b}"
LLAVA_API_NAME="\${LLAVA_API_NAME:-/add_text_1}"
LAVA_API_NAME="\${LAVA_API_NAME:-\$LLAVA_API_NAME}"

WORKER_ADDR="http://127.0.0.1:\${WORKER_PORT}"
WORKER_ADDR_ARG="--worker-address \${WORKER_ADDR}"

if [[ -z "\${LLAVA_MODEL_PATH:-}" ]]; then
  echo "ERROR: LLAVA_MODEL_PATH is not set (required to start model worker)" >&2
  echo "Set it to a local path or HF repo id, e.g.:"
  echo "  export LLAVA_MODEL_PATH=/workspace/models/llava-1.5-7b"
  echo "  export LLAVA_MODEL_PATH=liuhaotian/llava-v1.5-7b"
  exit 1
fi

assertPortFree "\$CONTROLLER_PORT"
assertPortFree "\$WORKER_PORT"
assertPortFree "\$WEB_PORT"

LOG_DIR="\${LOG_DIR:-\${WORKSPACE}/logs}"
mkdir -p "\$LOG_DIR"
LOG_CONTROLLER="\$LOG_DIR/llava.controller.\${CONTROLLER_PORT}.log"
LOG_WORKER="\$LOG_DIR/llava.worker.\${WORKER_PORT}.log"
LOG_WEB="\$LOG_DIR/llava.web.\${WEB_PORT}.log"
# --- controller ---
if tmux has-session -t "\$SESSION_CONTROLLER" 2>/dev/null; then
  echo "controller already running (tmux session: \$SESSION_CONTROLLER)"
else
  tmux new-session -d -s "\$SESSION_CONTROLLER" \\
    "bash -lc 'set -euo pipefail; cd \"\$LLAVA_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output \\
      python -m llava.serve.controller --host 0.0.0.0 --port \"\$CONTROLLER_PORT\" 2>&1 | tee -a \"\$LOG_CONTROLLER\"'"
  echo "controller started..."
fi

# --- worker ---
if tmux has-session -t "\$SESSION_WORKER" 2>/dev/null; then
  echo "worker already running (tmux session: \$SESSION_WORKER)"
else
  tmux new-session -d -s "\$SESSION_WORKER" \\
    "bash -lc 'set -euo pipefail; cd \"\$LLAVA_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output \\
      python -m llava.serve.model_worker --host 0.0.0.0 --port \"\$WORKER_PORT\" \\
        --controller http://127.0.0.1:\$CONTROLLER_PORT \\
        --model-path \"\$LLAVA_MODEL_PATH\" \\
        \$WORKER_ADDR_ARG 2>&1 | tee -a \"\$LOG_WORKER\"'"
  echo "worker started..."
fi

# --- web ---
if tmux has-session -t "\$SESSION_WEB" 2>/dev/null; then
  echo "web already running (tmux session: \$SESSION_WEB)"
else
  tmux new-session -d -s "\$SESSION_WEB" \\
    "bash -lc 'set -euo pipefail; cd \"\$LLAVA_DIR\"; \"\$CONDA_EXE\" run -n \"\$ENV_NAME\" --no-capture-output \\
      python -m llava.serve.gradio_web_server --host 0.0.0.0 --port \"\$WEB_PORT\" \\
        --model-list-mode reload \\
        --controller http://127.0.0.1:\$CONTROLLER_PORT 2>&1 | tee -a \"\$LOG_WEB\"'"
  echo "web started..."
fi

echo "done..."
EOF

  chmod +x "$outFile"
}

# ------------------------------------------------------------
# main
# ------------------------------------------------------------
main() {
  logTask "LLaVA"

  # Check if already done and not forcing
  if isStepDone "LLAVA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "llava already configured (use --force to rerun)"
    return 0
  fi

  LLAVA_VERSION="${LLAVA_VERSION:-1.5}"
  LLAVA_REF="${LLAVA_REF:-v1.5}"
  LLAVA_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA}"
  LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"

  log "llava dir: $LLAVA_DIR"
  log "llava env: $LLAVA_ENV_NAME"
  log "llava version: $LLAVA_VERSION"
  log "llava ref: $LLAVA_REF"

  # Ensure repo
  if ! isStepDone "LLAVA_REPO"; then
    log "ensuring llava repo"
    ensureGitRepo "$LLAVA_DIR" "https://github.com/haotian-liu/LLaVA.git" "LLaVA"

    local resolvedRef
    resolvedRef="$(resolveLlavaRef "$LLAVA_DIR" "$LLAVA_REF")"
    log "resolved ref: $resolvedRef"

    runSh "git -C \"$LLAVA_DIR\" checkout \"$resolvedRef\""
    runSh "git -C \"$LLAVA_DIR\" reset --hard \"$resolvedRef\""
    markStepDone "LLAVA_REPO"
  else
    log "llava repository already cloned"
  fi

  # Ensure conda environment
  if ! isStepDone "LLAVA_ENV"; then
    log "ensuring conda env: $LLAVA_ENV_NAME"
    ensureCondaEnv "$LLAVA_ENV_NAME" "3.10"
    markStepDone "LLAVA_ENV"
  else
    log "llava conda environment already created"
  fi

  # Upgrade pip/wheel/setuptools
  if ! isStepDone "LLAVA_PIP_UPGRADE"; then
    log "upgrading pip, wheel, and setuptools"
    condaEnvCmd "$LLAVA_ENV_NAME" python -m pip install --root-user-action=ignore -U pip wheel setuptools
    markStepDone "LLAVA_PIP_UPGRADE"
  else
    log "pip, wheel, and setuptools already upgraded"
  fi

  # Install LLaVA
  if ! isStepDone "LLAVA_INSTALL"; then
    log "installing llava (editable)"
    condaEnvCmd "$LLAVA_ENV_NAME" python -m pip install --root-user-action=ignore -e "$LLAVA_DIR"
    markStepDone "LLAVA_INSTALL"
  else
    log "llava already installed"
  fi

  # Verify installation
  if ! isStepDone "LLAVA_VERIFY"; then
    log "verifying llava import"
    if ! condaEnvCmd "$LLAVA_ENV_NAME" python -c 'import llava; print(llava.__file__)'; then
      warn "llava verification failed (continuing anyway)"
    fi
    markStepDone "LLAVA_VERIFY"
  else
    log "llava already verified"
  fi

  if ! isStepDone "LLAVA_PROTO_SENTENCEPIECE"; then
    log "installing protobuf and sentencepiece"
    condaEnvCmd "$LLAVA_ENV_NAME" python -m pip install --root-user-action=ignore -U protobuf sentencepiece
    markStepDone "LLAVA_PROTO_SENTENCEPIECE"
  else
    log "protobuf and sentencepiece already installed"
  fi

  local startScript="llavaStart.sh"
  log "writing llava start helper (local): $startScript"
  generateScript "$startScript"

  log "copying llava start helper to remote workspace: ${WORKSPACE_ROOT}/llavaStart.sh"
  runHostCmd scp "${SCP_OPTS[@]}" "$startScript" "${SSH_TARGET}:${WORKSPACE_ROOT}/llavaStart.sh"
  runSh "chmod +x '${WORKSPACE_ROOT}/llavaStart.sh'"

  markStepDone "LLAVA"
  log "llava step complete..."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
