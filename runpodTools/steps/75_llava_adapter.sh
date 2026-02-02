#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# 75_llava_adapter
# - generate adapter LOCALLY in current dir
# - scp to remote $WORKSPACE_ROOT
# - start uvicorn in tmux on pod
# ------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/run.sh"

# ------------------------------------------------------------
# helper: generate adapter python LOCALLY
# ------------------------------------------------------------
generateAdapter() {
  local outFile="$1"

  cat >"$outFile" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from gradio_client import Client, handle_file

GRADIO_INTERNAL = os.environ.get("LLAVA_GRADIO_URL") or os.environ.get("LAVA_GRADIO_URL") or "http://127.0.0.1:7003"
API_NAME = os.environ.get("LLAVA_API_NAME") or os.environ.get("LAVA_API_NAME") or "/add_text_1"
DEFAULT_PREPROCESS = os.environ.get("LLAVA_PREPROCESS", "Default")

app = FastAPI()

def _call_gradio(question: str, image_path: str, preprocess: str, api_name: str):
    c = Client(GRADIO_INTERNAL)

    # allow "add_text_1" or "/add_text_1" etc.
    if api_name and not api_name.startswith("/"):
        api_name = "/" + api_name 
    
    # IMPORTANT Image component expects ImageData, not a raw string
    img = handle_file(image_path)

    # signature for /add_text_1: (text, image_filepath, preprocess_mode)
    return c.predict(question, img, preprocess, api_name=api_name)

@app.post("/")
@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    question: str = Form("Describe the image in detail."),
    preprocess: str = Form(DEFAULT_PREPROCESS),
    api_name: str = Form(API_NAME),
):
    try:
        suffix = os.path.splitext(file.filename or "image.png")[1] or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        result = _call_gradio(question, tmp_path, preprocess, api_name)
        return JSONResponse({"ok": True, "result": result})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
PY

  chmod +x "$outFile"
}

# ------------------------------------------------------------
# helper: generate adapterStart.sh LOCALLY
# ------------------------------------------------------------
generateScript() {
  local outFile="$1"

  cat >"$outFile" <<'SH'
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
CONDA_DIR="${CONDA_DIR:-${WORKSPACE}/miniconda3}"
CONDA_EXE="${CONDA_EXE:-${CONDA_DIR}/bin/conda}"
ENV_NAME="${LLAVA_ENV_NAME:-llava}"

ADAPTER_PORT="${LLAVA_ADAPTER_PORT:-9188}"
SESSION="${LLAVA_ADAPTER_SESSION:-adapter}"

# defaults (can be overridden by environment)
export LLAVA_MODEL_PATH="${LLAVA_MODEL_PATH:-liuhaotian/llava-v1.5-7b}"
export LLAVA_GRADIO_URL="${LLAVA_GRADIO_URL:-http://127.0.0.1:7003}"
export LLAVA_API_NAME="${LLAVA_API_NAME:-/add_text_1}"
export LLAVA_PREPROCESS="${LLAVA_PREPROCESS:-Default}"

# compatibility with older variable names requested by user
export LAVA_GRADIO_URL="${LAVA_GRADIO_URL:-$LLAVA_GRADIO_URL}"
export LAVA_API_NAME="${LAVA_API_NAME:-$LLAVA_API_NAME}"

if ! command -v ss >/dev/null 2>&1; then
  echo "ERROR: ss not available; cannot check port usage" >&2
  exit 1
fi

if ss -ltn | awk '{print $4}' | grep -q ":${ADAPTER_PORT}$"; then
  echo "ERROR: port ${ADAPTER_PORT} already in use" >&2
  ss -ltnp | grep ":${ADAPTER_PORT}" || true
  exit 1
fi

LOG_DIR="${LOG_DIR:-${WORKSPACE}/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_DIR}/llava.adapter.${ADAPTER_PORT}.log"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not available; starting adapter in foreground"
  exec "$CONDA_EXE" run -n "$ENV_NAME" --no-capture-output \
    bash -lc "cd '${WORKSPACE}' && python -m uvicorn llavaAdapter:app --host 0.0.0.0 --port '${ADAPTER_PORT}'" \
    2>&1 | tee -a "$LOG_FILE"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "adapter already running (tmux session: $SESSION)"
  echo "log: $LOG_FILE"
  exit 0
fi

tmux new-session -d -s "$SESSION" \
  "bash -lc 'set -euo pipefail; cd "${WORKSPACE}"; "${CONDA_EXE}" run -n "${ENV_NAME}" --no-capture-output \
    python -m uvicorn llavaAdapter:app --host 0.0.0.0 --port "${ADAPTER_PORT}" 2>&1 | tee -a "${LOG_FILE}"'"

echo "adapter started (tmux session: $SESSION)"
echo "log: $LOG_FILE"
SH

  chmod +x "$outFile"
}


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
main() {

  # Check if already done and not forcing
  if isStepDone "LLAVA_ADAPTER" && [[ "${FORCE:-0}" != "1" ]]; then
    log "llava adapter already configured (use --force to rerun)"
    return 0
  fi

  LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
  LLAVA_ADAPTER_PORT="${LLAVA_ADAPTER_PORT:-9188}"
  LLAVA_GRADIO_URL="${LLAVA_GRADIO_URL:-http://127.0.0.1:7003}"
  LLAVA_API_NAME="${LLAVA_API_NAME:-/add_text_1}"
  LLAVA_PREPROCESS="${LLAVA_PREPROCESS:-Default}"
  SESSION="${LLAVA_ADAPTER_SESSION:-llava_adapter}"

  # Install adapter dependencies
  if ! isStepDone "LLAVA_ADAPTER_DEPS"; then
    log "ensure adapter deps (remote conda env: ${LLAVA_ENV_NAME})"
    condaEnvCmd "$LLAVA_ENV_NAME" python -m pip install --root-user-action=ignore -U fastapi uvicorn gradio_client python-multipart
    markStepDone "LLAVA_ADAPTER_DEPS"
  else
    log "llava adapter dependencies already installed"
  fi

  # Generate and upload adapter scripts
  # Always regenerate to capture potential configuration changes (ports, URLs, etc.)
  local llavaAdapter="./llavaAdapter.py"
  local adapterStart="./adapterStart.sh"

  log "create adapter script (local): ${llavaAdapter}"
  generateAdapter "$llavaAdapter"
  generateScript "$adapterStart"

  log "copy adapter to remote workspace: ${llavaAdapter}, ${adapterStart}"
  runHostCmd scp "${SCP_OPTS[@]}" "$llavaAdapter" "${SSH_TARGET}:${WORKSPACE_ROOT}/${llavaAdapter}"
  runHostCmd scp "${SCP_OPTS[@]}" "$adapterStart" "${SSH_TARGET}:${WORKSPACE_ROOT}/${adapterStart}"

  markStepDone "LLAVA_ADAPTER"
  log "done..."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
