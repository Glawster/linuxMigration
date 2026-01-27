mkdir -p ~/runpodLocalTest/workspace
mkdir -p ~/runpodLocalTest/root   # optional, if any /root writes

export WORKSPACE_ROOT="$HOME/runpodLocalTest/workspace"
export RUNPOD_DIR="$WORKSPACE_ROOT/runpodTools"
export CONDA_DIR="$WORKSPACE_ROOT/miniconda3"
export COMFY_DIR="$WORKSPACE_ROOT/ComfyUI"
export KOHYA_DIR="$WORKSPACE_ROOT/kohya_ss"   # if used later
export ENV_NAME="runpod"                      # from your 30_conda.sh

# Optional: clean previous runs
rm -rf "$WORKSPACE_ROOT" "$RUNPOD_DIR"
mkdir -p "$WORKSPACE_ROOT" "$RUNPOD_DIR"