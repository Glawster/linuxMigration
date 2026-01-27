export POD_ROOT="$HOME/runpodLocalTest" 
export WORKSPACE_ROOT="$POD_ROOT/workspace" 
export POD_HOME="$POD_ROOT/root" 
export RUNPOD_DIR="$WORKSPACE_ROOT/runpodTools"
export CONDA_DIR="$WORKSPACE_ROOT/miniconda3"
export COMFY_DIR="$WORKSPACE_ROOT/ComfyUI"
export KOHYA_DIR="$WORKSPACE_ROOT/kohya_ss"   # if used later
export ENV_NAME="runpod"                      # from your 30_conda.sh

mkdir -p "$WORKSPACE_ROOT"
mkdir -p "$POD_HOME"   # optional, if any /root writes