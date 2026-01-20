#!/usr/bin/env bash
# startComfyUI.sh
# Start ComfyUI in tmux session

set -euo pipefail

CONDA_DIR="${CONDA_DIR:-/workspace/miniconda3}"
ENV_NAME="${ENV_NAME:-runpod}"
COMFY_DIR="${COMFY_DIR:-/workspace/ComfyUI}"
PORT="${1:-8188}"

# shellcheck disable=SC1090
source "$CONDA_DIR/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
cd "$COMFY_DIR"

# Check for nvidia GPU
if command -v nvidia-smi >/dev/null 2>&1; then
  if ! nvidia-smi >/dev/null 2>&1; then
    echo "WARNING: nvidia-smi command found but failed to execute. No GPU detected."
    echo "ComfyUI may run in CPU mode which will be significantly slower."
  fi
else
  echo "WARNING: nvidia-smi not found. No NVIDIA GPU detected on this system."
  echo "ComfyUI will run in CPU mode which will be significantly slower."
  echo "For GPU acceleration, ensure NVIDIA drivers and CUDA are properly installed."
fi

if command -v tmux >/dev/null 2>&1; then
  if ! tmux has-session -t comfyui 2>/dev/null; then
    tmux new -d -s comfyui "source $CONDA_DIR/etc/profile.d/conda.sh && conda activate $ENV_NAME && python main.py --listen 0.0.0.0 --port $PORT"
    echo "comfyui started in tmux session: comfyui"
  else
    echo "comfyui tmux session already exists"
  fi
  echo "attach with: tmux attach -t comfyui"
else
  python main.py --listen 0.0.0.0 --port "$PORT"
fi
