#!/usr/bin/env bash
set -euo pipefail

# ------------------------------------------------------------
# testLlavaInstall.sh
# ------------------------------------------------------------
# Smoke-test LLaVA controller/worker + adapter using curl.
#
# Auto mode:
#   - If /workspace exists, assumes you're on the RunPod pod and tests localhost endpoints.
#   - Otherwise assumes you're on a local PC and tests via RunPod proxy URL(s).
#
# Examples:
#   Pod (auto-picks first /workspace/*.png if --img not supplied):
#     ./testLlavaInstall.sh
#     ./testLlavaInstall.sh --img /workspace/bp-13.png
#
#   Local (build adapter URL from PODID):
#     ./testLlavaInstall.sh --podid mcswsnfzk7f1h5 --img /home/andy/.../bp-13.png
#
#   Local (explicit adapter URL):
#     ./testLlavaInstall.sh --adapter-url "https://mcswsnfzk7f1h5-9188.proxy.runpod.net/analyze" --img /home/andy/.../bp-13.png
#
# Notes:
#   - Local mode tests adapter via proxy only, unless you also expose controller/worker and pass their URLs.
#   - The controller endpoints are POST (e.g. POST /list_models).
# ------------------------------------------------------------

log() { printf "%s\n" "$*"; }
hr() { printf "%s\n" "--------------------------------------------------------------------------------"; }
have_cmd() { command -v "$1" >/dev/null 2>&1; }
die() { log "ERROR: $*"; exit 1; }

is_pod() { [[ -d "/workspace" ]]; }

usage() {
  cat <<'EOF'
Usage:
  testLlavaInstall.sh [options]

Options:
  --img PATH                 Path to a PNG/JPG to test. On pod, if omitted, the script
                             auto-selects the first /workspace/*.png.
  --question TEXT            Prompt/question to ask the model (default: "Describe the image in detail.")
  --model-name NAME          Model name to use (default: "llava-v1.5-7b")

  --adapter-url URL          Adapter /analyze URL.
                             - Pod default:  http://127.0.0.1:9188/analyze
                             - Local:        if omitted, built from --podid

  --podid PODID              RunPod pod id used to build:
                               https://<PODID>-9188.proxy.runpod.net/analyze

  --controller-url URL       Controller URL (pod default: http://127.0.0.1:7001)
  --worker-url URL           Worker URL (pod default: http://127.0.0.1:7002)

  --max-time SECONDS         Curl max time for /analyze (default: 300)

  --help                     Show this help

Reminders:
  - Controller endpoints use POST (e.g. POST /list_models, POST /get_worker_address).
  - Local mode only validates the adapter unless you also expose controller/worker ports.
  - On pod, ensure controller (7001), worker (7002) and adapter (9188) are running.
EOF
}

# -----------------------------
# Defaults (can be overridden by args)
# -----------------------------
QUESTION="Describe the image in detail. Pay particular attention to the pose and the clothing worn."
MODEL_NAME="llava-v1.5-7b"
MAX_TIME="300"
IMG=""
PODID=""
ADAPTER_URL=""
CONTROLLER_URL=""
WORKER_URL=""

# -----------------------------
# Arg parsing
# -----------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    --img) IMG="${2:-}"; shift 2 ;;
    --question) QUESTION="${2:-}"; shift 2 ;;
    --model-name) MODEL_NAME="${2:-}"; shift 2 ;;
    --adapter-url) ADAPTER_URL="${2:-}"; shift 2 ;;
    --podid) PODID="${2:-}"; shift 2 ;;
    --controller-url) CONTROLLER_URL="${2:-}"; shift 2 ;;
    --worker-url) WORKER_URL="${2:-}"; shift 2 ;;
    --max-time) MAX_TIME="${2:-}"; shift 2 ;;
    --help|-h) usage; exit 0 ;;
    *) die "unknown argument: $1 (use --help)" ;;
  esac
done

# -----------------------------
# Mode detection + URLs
# -----------------------------
MODE="local"
if is_pod; then MODE="pod"; fi

# Auto-pick image on pod if not provided
if [[ "$MODE" == "pod" && -z "${IMG}" ]]; then
  # pick first png in /workspace
  first_png="$(ls -1 /workspace/*.png 2>/dev/null | head -n 1 || true)"
  if [[ -n "$first_png" ]]; then
    IMG="$first_png"
  fi
fi

# Require image now
if [[ -z "${IMG}" ]]; then
  die "no --img supplied. On local, set --img PATH. On pod, ensure a /workspace/*.png exists or pass --img."
fi
[[ -f "$IMG" ]] || die "file not found: $IMG"

if [[ "$MODE" == "pod" ]]; then
  CONTROLLER_URL="${CONTROLLER_URL:-http://127.0.0.1:7001}"
  WORKER_URL="${WORKER_URL:-http://127.0.0.1:7002}"
  ADAPTER_URL="${ADAPTER_URL:-http://127.0.0.1:9188/analyze}"
else
  # local PC: prefer explicit adapter URL, else build from PODID
  if [[ -z "${ADAPTER_URL}" ]]; then
    [[ -n "$PODID" ]] || die "local mode: set --adapter-url or --podid (use --help)"
    ADAPTER_URL="https://${PODID}-9188.proxy.runpod.net/analyze"
  fi
  # controller/worker optional in local mode
fi

curl_json() {
  local url="$1"; shift
  curl -sS -L -H "Accept: application/json" "$@" "$url"
}

show_kv() {
  local k="$1" v="$2"
  printf "%-18s %s\n" "${k}:" "${v}"
}

# -----------------------------
# Header
# -----------------------------
hr
log "LLaVA installation smoke test"
hr
show_kv "mode" "$MODE"
show_kv "img" "$IMG"
show_kv "adapter_url" "$ADAPTER_URL"
show_kv "model_name" "$MODEL_NAME"
show_kv "question" "$QUESTION"
if [[ "$MODE" == "pod" ]]; then
  show_kv "controller_url" "$CONTROLLER_URL"
  show_kv "worker_url" "$WORKER_URL"
fi
hr

JQ=""
if have_cmd jq; then
  JQ="jq"
else
  log "...note: jq not found; printing raw json"
fi

fail_count=0
run_test() {
  local name="$1"; shift
  hr
  log "$name"
  hr
  if "$@"; then
    log "...ok"
  else
    log "ERROR: test failed: $name"
    fail_count=$((fail_count+1))
  fi
}

test_port_listeners_pod() {
  if have_cmd ss; then
    ss -lntp | egrep ":(7001|7002|7003|9188)\b" || true
  else
    log "...ss not available"
  fi
  return 0
}

test_controller_list_models() {
  local out
  out="$(curl_json "$CONTROLLER_URL/list_models" -X POST --connect-timeout 5 --max-time 20 || true)"
  [[ -n "$out" ]] || return 1
  if [[ -n "$JQ" ]]; then echo "$out" | jq; else echo "$out"; fi
  echo "$out" | grep -q "\"models\"" || return 1
  return 0
}

test_controller_get_worker() {
  local payload out
  payload="$(printf '{"model":"%s"}' "$MODEL_NAME")"
  out="$(curl_json "$CONTROLLER_URL/get_worker_address" -X POST -H "Content-Type: application/json" -d "$payload" --connect-timeout 5 --max-time 20 || true)"
  [[ -n "$out" ]] || return 1
  if [[ -n "$JQ" ]]; then echo "$out" | jq; else echo "$out"; fi
  echo "$out" | grep -q "address" || echo "$out" | grep -q "worker_address"
}

test_worker_generate_pod() {
  if ! have_cmd python3; then
    log "...python3 not available, skipping"
    return 0
  fi

  IMG="$IMG" WORKER_URL="$WORKER_URL" MODEL_NAME="$MODEL_NAME" QUESTION="$QUESTION" python3 - <<'PY'
import base64, json, os, sys
import requests

img_path = os.environ["IMG"]
worker_url = os.environ["WORKER_URL"].rstrip("/")
model = os.environ["MODEL_NAME"]
question = os.environ["QUESTION"]
prompt = "<image>\n" + question

with open(img_path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode("utf-8")

payload = {
    "model": model,
    "prompt": prompt,
    "images": [b64],
    "temperature": 0.2,
    "top_p": 0.7,
    "max_new_tokens": 128,
}

try:
    r = requests.post(worker_url + "/worker_generate", json=payload, timeout=300)
    if r.status_code == 404:
        raise RuntimeError("no /worker_generate (404)")
    r.raise_for_status()
    print(r.text[:2000])
    sys.exit(0)
except Exception:
    r = requests.post(worker_url + "/worker_generate_stream", json=payload, stream=True, timeout=300)
    r.raise_for_status()
    text_parts = []
    for line in r.iter_lines(decode_unicode=True):
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "text" in obj:
                text_parts.append(obj["text"])
        except Exception:
            pass
    out = {"text": "".join(text_parts)}
    print(json.dumps(out)[:2000])
PY
}

test_adapter_analyze() {
  local out
  out="$(curl_json "$ADAPTER_URL" \
    -X POST \
    -F "file=@${IMG};type=image/png" \
    -F "question=${QUESTION}" \
    --connect-timeout 10 \
    --max-time "$MAX_TIME" || true)"
  [[ -n "$out" ]] || return 1
  if [[ -n "$JQ" ]]; then echo "$out" | jq; else echo "$out"; fi
  echo "$out" | grep -q '"ok":true' || echo "$out" | grep -q '"ok": true'
}

# -----------------------------
# Run tests
# -----------------------------
if [[ "$MODE" == "pod" ]]; then
  run_test "A) pod listeners (ss -lntp)" test_port_listeners_pod
  run_test "B) controller list_models (POST /list_models)" test_controller_list_models
  run_test "C) controller get_worker_address (POST /get_worker_address)" test_controller_get_worker
  run_test "D) worker generate (direct /worker_generate or /worker_generate_stream)" test_worker_generate_pod
else
  hr
  log "Note: local mode tests adapter via proxy only."
  log "      To test controller/worker directly from local, expose ports and pass --controller-url/--worker-url."
  hr
fi

run_test "E) adapter analyze (POST /analyze multipart upload)" test_adapter_analyze

hr
if [[ "$fail_count" -eq 0 ]]; then
  log "ALL TESTS PASSED"
else
  log "TESTS FAILED: ${fail_count}"
fi
hr
exit "$fail_count"
