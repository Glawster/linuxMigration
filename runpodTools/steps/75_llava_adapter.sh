#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# 75_llava_adapter
# - generate adapter LOCALLY in current dir
# - scp to remote $WORKSPACE_ROOT
# - start uvicorn in tmux on pod
# - using conda env llava
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

  # IMPORTANT:
  # - this heredoc is UNQUOTED so values like $LLAVA_CONTROLLER_URL get baked in,
  #   making llavaAdapter.py self-contained on the pod.
  cat >"$outFile" <<PY
#!/usr/bin/env python3
import os
import json
import io
import base64
import tempfile
import requests

from typing import Optional, Dict, Any
from PIL import Image
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse

app = FastAPI()

# Baked-in defaults from the step (self-contained on pod)
DEFAULT_CONTROLLER_URL = "${LLAVA_CONTROLLER_URL}"
DEFAULT_MODEL_NAME = "${LLAVA_MODEL_NAME}"
DEFAULT_TEMPERATURE = float("${LLAVA_TEMPERATURE:-0.2}")
DEFAULT_TOP_P = float("${LLAVA_TOP_P:-0.7}")
DEFAULT_MAX_TOKENS = int("${LLAVA_MAX_TOKENS:-256}")

IMAGE_TOKEN = "<image>"


def _env(name: str, fallback: str) -> str:
    v = os.environ.get(name)
    return v.strip() if isinstance(v, str) and v.strip() else fallback


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 60) -> Dict[str, Any]:
    r = requests.post(url, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _resolve_worker_url(controller_url: str, model_name: str) -> str:
    # Optional direct override (useful if controller is weird)
    override = os.environ.get("LLAVA_WORKER_URL", "").strip()
    if override:
        return override.rstrip("/")

    controller_url = controller_url.rstrip("/")
    obj = _post_json(f"{controller_url}/get_worker_address", {"model": model_name}, timeout=60)
    addr = (obj.get("address") or "").strip()
    if not addr:
        raise RuntimeError(f"controller returned no worker address: {obj}")
    return addr.rstrip("/")

def _clean_stream_text(full_text: str, question: str) -> str:
    t = (full_text or "").replace("\x00", "")
    t = t.replace("\r\n", "\n")

    s = t.lstrip()

    # 1) Strip leading "<image>" line if present (REAL newline)
    if s.startswith(IMAGE_TOKEN):
        # drop first line
        s = s.split("\n", 1)[1] if "\n" in s else ""
        s = s.lstrip()

    # 2) If the question is echoed right at the start, trim it safely
    q = (question or "").strip()
    if q:
        # allow optional leading newlines/spaces before the question
        s2 = s.lstrip("\n ").lstrip()
        if s2.startswith(q):
            s2 = s2[len(q):]
            s = s2

    # 3) Drop a couple of leading blank lines that often follow the echoed prompt
    s = s.lstrip("\n").lstrip()

    return s.strip()

def _call_worker(model_name: str, question: str, image_path: str) -> str:
    controller = _env("LLAVA_CONTROLLER_URL", DEFAULT_CONTROLLER_URL).rstrip("/")
    model = _env("LLAVA_MODEL_NAME", model_name)

    temperature = float(_env("LLAVA_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    top_p = float(_env("LLAVA_TOP_P", str(DEFAULT_TOP_P)))
    max_tokens = int(_env("LLAVA_MAX_TOKENS", str(DEFAULT_MAX_TOKENS)))

    worker = _resolve_worker_url(controller, model)

    image_b64 = ""
    if image_path:
        img = Image.open(image_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    if image_b64:
        thisImage = [image_b64]
        prompt = f"<image>\n{question}".strip()
    else:
        thisImage = []
        prompt = question.strip()

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "images": thisImage,
        "temperature": temperature,
        "top_p": top_p,
        "max_new_tokens": max_tokens,
        "stop": "###",
    }

    # never send None values
    payload = {k: v for k, v in payload.items() if v is not None}

    r = requests.post(
        f"{worker}/worker_generate_stream",
        json=payload,
        stream=True,
        timeout=300,
    )
    r.raise_for_status()

    last_obj: Optional[Dict[str, Any]] = None
    final_text: str = ""

    decoder = json.JSONDecoder()
    buf = ""
    abort = False

    for chunk in r.iter_content(chunk_size=None):
        if abort:
            break
        if not chunk:
            continue

        if isinstance(chunk, bytes):
            buf += chunk.decode("utf-8", errors="ignore")
        else:
            buf += str(chunk)

        buf = buf.replace("\r\n", "\n")

        while True:
            s = buf.lstrip()
            if not s:
                buf = ""
                break

            # handle SSE style: "data: {...}"
            if s.startswith("data:"):
                s = s[5:].lstrip()

            # if there is any non-json prefix, skip until first '{'
            if not s.startswith("{"):
                brace = s.find("{")
                if brace == -1:
                    # keep a small tail in case '{' splits across chunks
                    buf = s[-1024:]
                    break
                s = s[brace:]

            try:
                obj, idx = decoder.raw_decode(s)
            except json.JSONDecodeError:
                # need more bytes
                # keep a small tail so buffer doesn't grow forever
                if len(buf) > 10_000_000:
                    buf = buf[-1_000_000:]
                break

            # advance buffer by consumed chars (account for lstrip + skipped prefix)
            consumed = len(buf) - len(s) + idx
            buf = buf[consumed:]

            if not isinstance(obj, dict):
                continue

            last_obj = obj

            t = obj.get("text")
            if isinstance(t, str) and t.strip():
                final_text = t

                # treat high-traffic sentinel as a real error
                if "NETWORK ERROR DUE TO HIGH TRAFFIC" in final_text:
                    abort = True
                    break

            ec = obj.get("error_code", 0)
            if ec not in (0, None):
                abort = True
                break

    if not final_text or "NETWORK ERROR DUE TO HIGH TRAFFIC" in final_text:
        raise RuntimeError(f"worker returned no text (last_obj={last_obj})")

    return _clean_stream_text(final_text, question)

DEFAULT_QUESTION = _env("LLAVA_QUESTION", "Describe the image in detail.")


@app.post("/")
@app.post("/analyze")
async def analyze(
    # accept either "file" OR "image" from multipart form
    file: Optional[UploadFile] = File(None),
    image: Optional[UploadFile] = File(None),
    question: str = Form(DEFAULT_QUESTION),
):
    tmp_path: Optional[str] = None
    try:
        up = file or image
        if up is None:
            return JSONResponse({"ok": False, "error": "missing upload field: provide multipart 'file' or 'image'"},
                                status_code=400)

        suffix = os.path.splitext(up.filename or "image.png")[1] or ".png"
        data = await up.read()
        if isinstance(data, str):
            data = data.encode("utf-8", errors="ignore")

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        result_text = _call_worker(DEFAULT_MODEL_NAME, question, tmp_path)
        return {"ok": True, "result": result_text}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
PY

  chmod +x "$outFile" || true
}

# ------------------------------------------------------------
# helper: generate adapterStart.sh LOCALLY
# ------------------------------------------------------------
generateScript() {
  local outFile="$1"

  bakedEnvName="${LLAVA_ENV_NAME}"

  cat >"$outFile" <<SH
#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="\${WORKSPACE:-/workspace}"
CONDA_DIR="\${CONDA_DIR:-\${WORKSPACE}/miniconda3}"
CONDA_EXE="\${CONDA_EXE:-\${CONDA_DIR}/bin/conda}"
LLAVA_ENV_NAME="\${LLAVA_ENV_NAME:-${bakedEnvName}}"

ADAPTER_PORT="\${LLAVA_ADAPTER_PORT:-9188}"
SESSION="\${LLAVA_ADAPTER_SESSION:-adapter}"

# defaults (can be overridden by environment)
export LLAVA_CONTROLLER_URL="\${LLAVA_CONTROLLER_URL:-http://127.0.0.1:7001}"
export LLAVA_MODEL_NAME="\${LLAVA_MODEL_NAME:-llava-v1.5-7b}"

# Optional: override worker URL if controller returns bogus values
# (leave empty to use controller)
export LLAVA_WORKER_URL="\${LLAVA_WORKER_URL:-}"

export LLAVA_QUESTION="\${LLAVA_QUESTION:-Describe the image in detail.}"
export LLAVA_TEMPERATURE="\${LLAVA_TEMPERATURE:-0.2}"
export LLAVA_TOP_P="\${LLAVA_TOP_P:-0.7}"
export LLAVA_MAX_TOKENS="\${LLAVA_MAX_TOKENS:-512}"

if ! command -v ss >/dev/null 2>&1; then
  echo "ERROR: ss not available; cannot check port usage" >&2
  exit 1
fi

if ss -ltn | awk '{print \$4}' | grep -q ":\${ADAPTER_PORT}$"; then
  echo "ERROR: port \${ADAPTER_PORT} already in use" >&2
  ss -ltnp | grep ":\${ADAPTER_PORT}" || true
  exit 1
fi

LOG_DIR="\${LOG_DIR:-\${WORKSPACE}/logs}"
mkdir -p "\$LOG_DIR"
LOG_FILE="\${LOG_DIR}/adapter.\${ADAPTER_PORT}.log"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not available; starting adapter in foreground"
  exec "\$CONDA_EXE" run -n "\$LLAVA_ENV_NAME" --no-capture-output \
    bash -lc "cd '\${WORKSPACE}' && python -m uvicorn llavaAdapter:app --host 0.0.0.0 --port '\${ADAPTER_PORT}'" \
    2>&1 | tee -a "\$LOG_FILE"
fi

if tmux has-session -t "\$SESSION" 2>/dev/null; then
  echo "adapter already running (tmux session: \$SESSION)"
  echo "log: \$LOG_FILE"
  exit 0
fi

tmux new-session -d -s "\$SESSION" \
  "bash -lc 'set -euo pipefail; cd \"\${WORKSPACE}\"; \"\${CONDA_EXE}\" run -n \"\${LLAVA_ENV_NAME}\" --no-capture-output \
    python -m uvicorn llavaAdapter:app --host 0.0.0.0 --port \"\${ADAPTER_PORT}\" 2>&1 | tee -a \"\${LOG_FILE}\"'"

echo "adapter started (tmux session: \$SESSION)"
echo "log: \$LOG_FILE"
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

  JOYFUL="${JOYFUL:-0}"

  # joyful mode is enabled via env var JOYFUL=1 (bootstrap may also set it via --joyful)
  if [[ "$JOYFUL" == "1" ]]; then
    LLAVA_VERSION="${LLAVA_VERSION:-joycaption-alpha-two}"   # or beta-one, your choice
    LLAVA_REF="${LLAVA_REF:-main}"                           # no specific tag needed
    LLAVA_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA-JoyCaption}"  # different dir to avoid conflict
    LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-joycaption}"
    LLAVA_MODEL_PATH="${LLAVA_MODEL_PATH:-fancyfeast/llama-joycaption-alpha-two-hf-llava}"
    LLAVA_MODEL_NAME="${LLAVA_MODEL_NAME:-joycaption-alpha-two}"
  else
    LLAVA_VERSION="${LLAVA_VERSION:-1.5}"
    LLAVA_REF="${LLAVA_REF:-v1.5}"
    LLAVA_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA}"
    LLAVA_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
    LLAVA_MODEL_PATH="${LLAVA_MODEL_PATH:-liuhaotian/llava-v1.5-7b}"
    LLAVA_MODEL_NAME="${LLAVA_MODEL_NAME:-llava-v1.5-7b}"
  fi
  LLAVA_ADAPTER_PORT="${LLAVA_ADAPTER_PORT:-9188}"  
  LLAVA_CONTROLLER_URL="${LLAVA_CONTROLLER_URL:-http://127.0.0.1:7001}"

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
