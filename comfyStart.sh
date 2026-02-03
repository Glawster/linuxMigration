#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="/workspace"
COMFY_DIR="$WORKSPACE/ComfyUI"
CONDA_DIR="$WORKSPACE/miniconda3"
CONDA_EXE="$CONDA_DIR/bin/conda"
ENV_NAME="comfyui"
PORT="8188"
SESSION="comfyui"

if ! command -v ss >/dev/null 2>&1; then
  echo "ERROR: ss not available; cannot check port usage" >&2
  exit 1
fi

if ss -ltn | awk '{print $4}' | grep -q ":${PORT}$"; then
  echo "ERROR: port ${PORT} already in use"
  ss -ltnp | grep ":${PORT}" || true
  exit 1
fi

if [[ ! -d "$COMFY_DIR" ]]; then
  echo "ERROR: ComfyUI directory not found: $COMFY_DIR" >&2
  exit 1
fi

if [[ ! -x "$CONDA_EXE" ]]; then
  echo "ERROR: conda not found/executable at $CONDA_EXE" >&2
  exit 1
fi

LOG_DIR="$WORKSPACE/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/comfyui.${PORT}.log"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux not available; starting ComfyUI in foreground"
  exec "$CONDA_EXE" run -n "$ENV_NAME" --no-capture-output \
    bash -lc "cd '$COMFY_DIR' && python main.py --listen 0.0.0.0 --port '$PORT'" \
    2>&1 | tee -a "$LOG_FILE"
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "comfyui already running (tmux session: $SESSION)"
  echo "log: $LOG_FILE"
  exit 0
fi

tmux new-session -d -s "$SESSION" \
  "bash -lc 'set -euo pipefail; cd \"$COMFY_DIR\"; \"$CONDA_EXE\" run -n \"$ENV_NAME\" --no-capture-output python main.py --listen 0.0.0.0 --port \"$PORT\" 2>&1 | tee -a \"$LOG_FILE\"'"

echo "comfyui started (tmux session: $SESSION)"
echo "log: $LOG_FILE"
