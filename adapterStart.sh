#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${WORKSPACE:-/workspace}"
CONDA_DIR="${CONDA_DIR:-${WORKSPACE}/miniconda3}"
CONDA_EXE="${CONDA_EXE:-${CONDA_DIR}/bin/conda}"
ENV_NAME="${ENV_NAME:-llava}"

ADAPTER_PORT="${LLAVA_ADAPTER_PORT:-9188}"
SESSION="${LLAVA_ADAPTER_SESSION:-adapter}"

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
