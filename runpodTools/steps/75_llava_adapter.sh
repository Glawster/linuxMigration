#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# 75_llava_adapter
# - generate adapter LOCALLY in current dir
# - scp to remote $WORKSPACE_ROOT
# - start uvicorn in tmux on pod
# ------------------------------------------------------------

stepName="75_llava_adapter"

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
generateScript() {
  local outFile="$1"

  cat >"$outFile" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from gradio_client import Client

GRADIO_INTERNAL = os.environ.get("LLAVA_GRADIO_URL", "http://127.0.0.1:7003")
API_NAME = os.environ.get("LLAVA_API_NAME", "/add_text_1")
DEFAULT_PREPROCESS = os.environ.get("LLAVA_PREPROCESS", "Default")

app = FastAPI()

def _call_gradio(question: str, image_path: str, preprocess: str, api_name: str):
    c = Client(GRADIO_INTERNAL)
    # signature for /add_text_1: (text, image_filepath, preprocess_mode)
    return c.predict(question, image_path, preprocess, api_name=api_name)

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
# main
# ------------------------------------------------------------
main() {

  LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
  LLAVA_ADAPTER_PORT="${LLAVA_ADAPTER_PORT:-9188}"
  LLAVA_GRADIO_URL="${LLAVA_GRADIO_URL:-http://127.0.0.1:7003}"
  LLAVA_API_NAME="${LLAVA_API_NAME:-/add_text_1}"
  LLAVA_PREPROCESS="${LLAVA_PREPROCESS:-Default}"
  SESSION="${LLAVA_ADAPTER_SESSION:-llava_adapter}"

  log "ensure adapter deps (remote conda env: ${LLAVA_ENV_NAME})"
  condaEnvCmd "$LLAVA_ENV_NAME" python -m pip install -U fastapi uvicorn gradio_client python-multipart
  log "Llava Adapter dependencies are ok"

  local localAdapter="./llavaAdapter.py"
  local remoteAdapter="${WORKSPACE_ROOT}/llavaAdapter.py"

  log "create adapter script (local): ${localAdapter}"
  generateScript "$localAdapter"

  log "copy adapter to remote workspace: ${remoteAdapter}"
  runHostCmd scp "${SCP_OPTS[@]}" "$localAdapter" "${SSH_TARGET}:${remoteAdapter}"
  runSh "chmod +x '${remoteAdapter}'"

  log "start adapter in tmux (remote): session=${SESSION} port=${LLAVA_ADAPTER_PORT}"
  runSh "$(cat <<EOF
set -euo pipefail

if command -v fuser >/dev/null 2>&1; then
  fuser -k ${LLAVA_ADAPTER_PORT}/tcp >/dev/null 2>&1 || true
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "ERROR: tmux not installed" >&2
  exit 1
fi

if tmux has-session -t "${SESSION}" 2>/dev/null; then
  tmux kill-session -t "${SESSION}"
fi

tmux new-session -d -s "${SESSION}" \\
  "bash -lc 'set -euo pipefail; \\
    export LLAVA_GRADIO_URL=\"${LLAVA_GRADIO_URL}\" LLAVA_API_NAME=\"${LLAVA_API_NAME}\" LLAVA_PREPROCESS=\"${LLAVA_PREPROCESS}\"; \\
    cd \"${WORKSPACE_ROOT}\"; \\
    \"${WORKSPACE_ROOT}/miniconda3/bin/conda\" run -n \"${LLAVA_ENV_NAME}\" --no-capture-output \\
      python -m uvicorn llavaAdapter:app --host 0.0.0.0 --port ${LLAVA_ADAPTER_PORT}'"

echo "adapter started..."
EOF
)"

  log "probe adapter on pod"
  runSh "curl -s -o /dev/null -w 'adapter http: %{http_code}\n' http://127.0.0.1:${LLAVA_ADAPTER_PORT}/analyze || true"

  log "done..."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
