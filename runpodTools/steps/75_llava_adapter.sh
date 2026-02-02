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
generateAdapter() {
  local outFile="$1"

  cat >"$outFile" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import os
import tempfile
from typing import Optional

import requests
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

# ------------------------------------------------------------
# LLaVA controller/worker API (no Gradio)
# ------------------------------------------------------------
CONTROLLER_INTERNAL = os.environ.get("LLAVA_CONTROLLER_URL", "http://127.0.0.1:7001").rstrip("/")
MODEL_NAME = os.environ.get("LLAVA_MODEL_NAME", "llava-v1.5-7b")

# Optional override: if controller returns nonsense, force worker URL
WORKER_FALLBACK = os.environ.get("LLAVA_WORKER_URL", "").strip().rstrip("/")

DEFAULT_QUESTION = os.environ.get("LLAVA_QUESTION", "Describe the image in detail.")
DEFAULT_TEMPERATURE = float(os.environ.get("LLAVA_TEMPERATURE", "0.2"))
DEFAULT_TOP_P = float(os.environ.get("LLAVA_TOP_P", "0.7"))
DEFAULT_MAX_TOKENS = int(os.environ.get("LLAVA_MAX_TOKENS", "512"))

# LLaVA typically expects an <image> token in the prompt for multimodal requests
IMAGE_TOKEN = os.environ.get("LLAVA_IMAGE_TOKEN", "<image>")

app = FastAPI()

def _get_worker_address(model_name: str) -> str:
    r = requests.post(
        f"{CONTROLLER_INTERNAL}/get_worker_address",
        json={"model": model_name},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    addr = (data.get("address") or data.get("worker_address") or "").strip()

    # normalize localhost -> 127.0.0.1 (critical for pods)
    addr = addr.replace("http://localhost", "http://127.0.0.1").rstrip("/")

    # fallback if controller returned empty or unusable
    if not addr and WORKER_FALLBACK:
        return WORKER_FALLBACK

    if not addr:
        raise RuntimeError(f"no worker address in response: {data}")

    return addr

def _call_worker(model: str, question: str, image_path: str) -> str:

    WORKER_URL = _get_worker_address(model)

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    payload = {
        "model": model,
        "prompt": f"{IMAGE_TOKEN}\n{question}",
        "images": [image_b64],
        "temperature": DEFAULT_TEMPERATURE,
        "top_p": DEFAULT_TOP_P,
        "max_new_tokens": DEFAULT_MAX_TOKENS,
        "stop": "###",
        "stop_str": "###",
        "stop_sequences": ["###"],
    }

    resp = requests.post(
        f"{WORKER_URL}/worker_generate_stream",
        json=payload,
        stream=True,
        timeout=300,
    )

    resp.raise_for_status()

    last_obj = None
    final_text = ""

    for raw in resp.iter_lines(decode_unicode=True):
        if not raw:
            continue

        line = raw.strip()

        # Some servers send SSE lines: "data: {...}"
        if line.startswith("data:"):
            line = line[len("data:"):].strip()

        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            # Keep going, but if we end with nothing this will help debugging
            continue

        last_obj = obj

        t = obj.get("text")
        if isinstance(t, str) and t:
            # LLaVA streams cumulative text; keep the latest
            final_text = t

        ec = obj.get("error_code", 0)
        if ec not in (0, None):
            # stop early on worker-reported error
            break

    if not final_text:
        # last resort: capture a snippet of response for debugging
        try:
            snippet = resp.text[:500]
        except Exception:
            snippet = "<unable to read resp.text>"
        raise RuntimeError(f"worker returned no text (last_obj={last_obj}, snippet={snippet!r})")

    return final_text.strip()



@app.post("/")
@app.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    question: str = Form(DEFAULT_QUESTION),
):
    tmp_path: Optional[str] = None
    try:
        suffix = os.path.splitext(file.filename or "image.png")[1] or ".png"
        data = await file.read()

        # Defensive: ensure bytes
        if isinstance(data, str):
            data = data.encode("utf-8", errors="ignore")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        result = _call_worker(MODEL_NAME, question, tmp_path)
        return {"ok": True, "result": result}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
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
# defaults (can be overridden by environment)
export LLAVA_CONTROLLER_URL="${LLAVA_CONTROLLER_URL:-http://127.0.0.1:7001}"
export LLAVA_MODEL_NAME="${LLAVA_MODEL_NAME:-llava-v1.5-7b}"

# Optional: override worker URL if controller returns bogus values
# (leave empty to use controller)
export LLAVA_WORKER_URL="${LLAVA_WORKER_URL:-}"

export LLAVA_QUESTION="${LLAVA_QUESTION:-Describe the image in detail.}"
export LLAVA_TEMPERATURE="${LLAVA_TEMPERATURE:-0.2}"
export LLAVA_TOP_P="${LLAVA_TOP_P:-0.7}"
export LLAVA_MAX_TOKENS="${LLAVA_MAX_TOKENS:-512}"

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
  LLAVA_CONTROLLER_URL="${LLAVA_CONTROLLER_URL:-http://127.0.0.1:7001}"
  LLAVA_MODEL_NAME="${LLAVA_MODEL_NAME:-llava-v1.5-7b}"
  SESSION="${LLAVA_ADAPTER_SESSION:-adapter}"

  log "ensure adapter deps (remote conda env: ${LLAVA_ENV_NAME})"
  if ! isStepDone "LLAVA_ADAPTER_DEPS"; then
    condaEnvCmd "$LLAVA_ENV_NAME" python -m pip install --root-user-action=ignore -U requests fastapi uvicorn python-multipart
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
