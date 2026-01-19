#!/usr/bin/env bash
# runpodBootstrap.sh
#
# Local helper:
# - parses target + ssh options
# - SSHs to the pod and writes remote setup scripts using heredocs (no scp)
# - optionally runs the remote setup
#
# Defaults:
#   --comfyui enabled
#   --run enabled
#   --kohya disabled (optional)
#
# Usage:
#   ./runpodBootstrap.sh [options] user@host -p PORT [-i KEY]
#
# Options:
#   --comfyui        enable ComfyUI setup (default)
#   --no-comfyui     disable ComfyUI setup
#   --kohya          enable kohya setup (default off)
#   --run            run remote setup after writing (default)
#   --no-run         only write scripts, don't execute
#   --dry-run        do not modify remote; print ssh commands and do a connectivity check
#   -h, --help       help
#
# Example:
#   ./runpodBootstrap.sh root@213.192.2.88 -p 40023 -i ~/.ssh/id_ed25519
#
# Dry run (validate command / connectivity):
#   ./runpodBootstrap.sh --dry-run root@213.192.2.88 -p 40023 -i ~/.ssh/id_ed25519

# use this rsync command (port number and ip address adjusted as needed)... 
#
# rsync -avP --partial --inplace --ignore-existing \
#   -e "ssh -p 40190 -i ~/.ssh/id_ed25519" \
#   models/ root@213.192.2.88:/workspace/ComfyUI/models/

# starting comfui...
#   tmux kill-session -t comfyui 2>/dev/null || true
#   bash /workspace/startComfyUI.sh --conda-dir /workspace/miniconda3 --env-name runpod --port 8188

set -euo pipefail

# ---------------------------
# Defaults
# ---------------------------
ENABLE_COMFYUI=1
ENABLE_KOHYA=0
RUN_REMOTE=1
DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="[]"
MODEL_ROOT=""

TARGET=""
SSH_PORT="22"
SSH_IDENTITY=""

usage() {
  sed -n '2,70p' "$0"
  exit 0
}

# ---------------------------
# Parse args
# ---------------------------
if [[ $# -lt 1 ]]; then
  usage
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --comfyui) ENABLE_COMFYUI=1; shift ;;
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;
    --kohya) ENABLE_KOHYA=1; shift ;;
    --run) RUN_REMOTE=1; shift ;;
    --no-run) RUN_REMOTE=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --model-root) MODEL_ROOT="$2"; shift 2 ;;
    -p) SSH_PORT="$2"; shift 2 ;;
    -i) SSH_IDENTITY="$2"; shift 2 ;;
    -h|--help) usage ;;
    *)
      if [[ -z "$TARGET" ]]; then
        TARGET="$1"
        shift
      else
        echo "ERROR: unexpected arg: $1"
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: missing user@host"
  exit 1
fi

SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=accept-new)
if [[ -n "$SSH_IDENTITY" ]]; then
  SSH_OPTS+=(-i "$SSH_IDENTITY")
fi

echo "target      : ${TARGET}:${SSH_PORT}"
echo "identity    : ${SSH_IDENTITY:-<default>}"
echo "comfyui     : ${ENABLE_COMFYUI}"
echo "kohya       : ${ENABLE_KOHYA}"
echo "run remote  : ${RUN_REMOTE}"
echo "dry run     : ${DRY_RUN}"
echo

# ---------------------------
# Helper to run or print commands
# ---------------------------
run_local() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "${DRY_PREFIX} $*"
  else
    "$@"
  fi
}

ssh_cmd() {
  # wrapper to show exactly what we'd run
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "${DRY_PREFIX} ssh ${SSH_OPTS[*]} ${TARGET} <remote-command>"
    return 0
  fi
  ssh "${SSH_OPTS[@]}" "$TARGET" "$@"
}

# ---------------------------
# Connectivity check (safe even in dry-run)
# ---------------------------
echo "checking ssh connectivity..."
echo "${SSH_OPTS[@]}" "$TARGET" "echo connected && uname -a" >/dev/null
echo "connected..."
echo

# ---------------------------
# Remote script contents
# ---------------------------
# Remote orchestrator: /workspace/runpodSetup.sh
# - Enables comfyui by default
# - Enables kohya optionally
# - Supports --dry-run to avoid making changes on the pod
REMOTE_SETUP_SCRIPT=$'#!/usr/bin/env bash\n\
# /workspace/runpodSetup.sh\n\
# Runs on the POD.\n\
# Default: ComfyUI enabled, kohya disabled.\n\
# Use: bash /workspace/runpodSetup.sh [--kohya] [--no-comfyui] [--no-run] [--dry-run]\n\
\n\
set -euo pipefail\n\
\n\
ENABLE_COMFYUI=1\n\
ENABLE_KOHYA=0\n\
RUN_REMOTE=1\n\
DRY_RUN=0\n\
\n\
usage() {\n\
  echo \"usage: $0 [--kohya] [--no-comfyui] [--no-run] [--dry-run]\";\n\
}\n\
\n\
while [[ $# -gt 0 ]]; do\n\
  case \"$1\" in\n\
    --kohya) ENABLE_KOHYA=1; shift ;;\n\
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;\n\
    --no-run) RUN_REMOTE=0; shift ;;\n\
    --dry-run) DRY_RUN=1; shift ;;\n\
    -h|--help) usage; exit 0 ;;\n\
    *) echo \"ERROR: unknown arg: $1\"; usage; exit 1 ;;\n\
  esac\n\
done\n\
\n\
log(){ echo -e \"\\n==> $*\\n\"; }\n\
run(){ if [[ \"$DRY_RUN\" == \"1\" ]]; then echo \"[] $*\"; else \"$@\"; fi }\n\
\n\
log \"checking gpu\"\n\
if command -v nvidia-smi >/dev/null 2>&1; then run nvidia-smi || true; else echo \"WARNING: nvidia-smi not found\"; fi\n\
\n\
log \"ensuring base tools\"\n\
if command -v apt-get >/dev/null 2>&1; then\n\
  run apt-get update -y\n\
  run apt-get install -y git wget rsync tmux htop unzip build-essential python3-venv python3-pip ca-certificates\n\
else\n\
  echo \"WARNING: apt-get not found. Assuming base image has tools.\"\n\
fi\n\
\n\
# ---------------------------
# ComfyUI
# ---------------------------

log "installing ComfyUI-Manager (custom node)"

COMFY_DIR="/workspace/ComfyUI"
MANAGER_DIR="${COMFY_DIR}/custom_nodes/ComfyUI-Manager"

if [[ ! -d "${MANAGER_DIR}/.git" ]]; then
  run git clone https://github.com/ltdrdata/ComfyUI-Manager.git "${MANAGER_DIR}"
else
  run bash -lc "cd \"${MANAGER_DIR}\" && git pull --ff-only || true"
fi

# Install manager python deps if present
if [[ -f "${MANAGER_DIR}/requirements.txt" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[] python -m pip install --upgrade pip"
    echo "[] pip install -r ${MANAGER_DIR}/requirements.txt"
  else
    # venv already activated above
    python -m pip install --upgrade pip
    pip install -r "${MANAGER_DIR}/requirements.txt"
  fi
fi
\n\
if [[ "$ENABLE_COMFYUI" == "1" ]]; then
  log "setting up comfyui"

  COMFY_ARGS=()
  if [[ "$DRY_RUN" == "1" ]]; then
    COMFY_ARGS+=(--dry-run)
  fi

  run bash /workspace/runpodComfySetup.sh "${COMFY_ARGS[@]}"

  if [[ "$RUN_REMOTE" == "1" ]]; then
    log "starting comfyui"
    run bash /workspace/startComfyUI.sh "${COMFY_ARGS[@]}" 8188
  fi
fi
\n\
if [[ "$ENABLE_KOHYA" == "1" ]]; then
  log "setting up kohya"

  KOHYA_ARGS=()
  if [[ "$DRY_RUN" == "1" ]]; then
    KOHYA_ARGS+=(--dry-run)
  fi

  run bash /workspace/runpodKohyaSetup.sh "${KOHYA_ARGS[@]}"
fi
\n\
log \"done\"\n\
'

# Remote ComfyUI installer: /workspace/runpodComfySetup.sh
REMOTE_COMFY_SETUP_SCRIPT=$'#!/usr/bin/env bash\n\
# /workspace/runpodComfySetup.sh\n\
# Install ComfyUI in a venv and CUDA torch.\n\
\n\
set -euo pipefail\n\
DRY_RUN=0\n\
if [[ ${1:-} == \"--dry-run\" ]]; then DRY_RUN=1; shift; fi\n\
\n\
COMFY_DIR=\"${COMFY_DIR:-/workspace/ComfyUI}\"\n\
COMFY_VENV_DIR=\"${COMFY_VENV_DIR:-/workspace/venvs/comfyui}\"\n\
TORCH_CUDA_INDEX_URL=\"${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}\"\n\
\n\
log(){ echo -e \"\\n==> $*\\n\"; }\n\
run(){ if [[ \"$DRY_RUN\" == \"1\" ]]; then echo \"[] $*\"; else \"$@\"; fi }\n\
\n\
log \"cloning/updating comfyui\"\n\
run mkdir -p \"$(dirname \"$COMFY_VENV_DIR\")\"\n\
\n\
if [[ ! -d \"$COMFY_DIR/.git\" ]]; then\n\
  run git clone https://github.com/comfyanonymous/ComfyUI.git \"$COMFY_DIR\"\n\
else\n\
  run bash -lc \"cd \\\"$COMFY_DIR\\\" && git pull --ff-only || true\"\n\
fi\n\
\n\
log \"creating venv\"\n\
run python3 -m venv \"$COMFY_VENV_DIR\"\n\
\n\
log \"installing deps\"\n\
if [[ \"$DRY_RUN\" == \"1\" ]]; then\n\
  echo \"[] source $COMFY_VENV_DIR/bin/activate && pip install ...\"\n\
else\n\
  # shellcheck disable=SC1090\n\
  source \"$COMFY_VENV_DIR/bin/activate\"\n\
  python -m pip install --upgrade pip wheel\n\
  pip install -U torch torchvision torchaudio --index-url \"$TORCH_CUDA_INDEX_URL\"\n\
  pip install -r \"$COMFY_DIR/requirements.txt\"\n\
  python -c \"import torch; print(\\\"cuda?\\\", torch.cuda.is_available()); print(\\\"gpu:\\\", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)\"\n\
fi\n\
\n\
log \"comfyui setup complete\"\n\
'

# Remote ComfyUI starter: /workspace/startComfyUI.sh
REMOTE_COMFY_START_SCRIPT=$'#!/usr/bin/env bash\n\
# /workspace/startComfyUI.sh\n\
# Start ComfyUI on 0.0.0.0:8188 (tmux).\n\
\n\
set -euo pipefail\n\
DRY_RUN=0\n\
if [[ ${1:-} == \"--dry-run\" ]]; then DRY_RUN=1; shift; fi\n\
\n\
PORT=\"${1:-8188}\"\n\
COMFY_DIR=\"${COMFY_DIR:-/workspace/ComfyUI}\"\n\
COMFY_VENV_DIR=\"${COMFY_VENV_DIR:-/workspace/venvs/comfyui}\"\n\
\n\
run(){ if [[ \"$DRY_RUN\" == \"1\" ]]; then echo \"[] $*\"; else \"$@\"; fi }\n\
\n\
if [[ \"$DRY_RUN\" == \"1\" ]]; then\n\
  echo \"[] would start comfyui in tmux on port $PORT\"\n\
  exit 0\n\
fi\n\
\n\
# shellcheck disable=SC1090\n\
source \"$COMFY_VENV_DIR/bin/activate\"\n\
cd \"$COMFY_DIR\"\n\
\n\
if command -v tmux >/dev/null 2>&1; then\n\
  if ! tmux has-session -t comfyui 2>/dev/null; then\n\
    tmux new -d -s comfyui \"python main.py --listen 0.0.0.0 --port $PORT\"\n\
    echo \"comfyui started in tmux session: comfyui\"\n\
  else\n\
    echo \"comfyui tmux session already exists\"\n\
  fi\n\
  echo \"attach with: tmux attach -t comfyui\"\n\
else\n\
  python main.py --listen 0.0.0.0 --port \"$PORT\"\n\
fi\n\
'

# Remote kohya installer placeholder: /workspace/runpodKohyaSetup.sh
# (kept minimal here; you can paste your current one into this slot if you want a 1:1 match)
REMOTE_KOHYA_SETUP_SCRIPT=$'#!/usr/bin/env bash\n\
# /workspace/runpodKohyaSetup.sh\n\
# Placeholder: keep your existing kohya setup script content here.\n\
# Supports --dry-run.\n\
\n\
set -euo pipefail\n\
DRY_RUN=0\n\
if [[ ${1:-} == \"--dry-run\" ]]; then DRY_RUN=1; shift; fi\n\
\n\
run(){ if [[ \"$DRY_RUN\" == \"1\" ]]; then echo \"[] $*\"; else \"$@\"; fi }\n\
echo \"kohya setup script placeholder...\"\n\
echo \"(replace REMOTE_KOHYA_SETUP_SCRIPT content with your real kohya installer)\"\n\
'

# ---------------------------
# Write scripts to remote (or print command in dry-run)
# ---------------------------
write_remote_file() {
  local remote_path="$1"
  local content="$2"

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[] would write remote file: ${remote_path}"
    cat <<CMD
ssh ${SSH_OPTS[*]} ${TARGET} 'cat > ${remote_path} <<'"'"'EOF'"'"'
${content}
EOF
chmod +x ${remote_path}'
CMD
    return 0
  fi

  # Use a single SSH session to write the file via heredoc
  ssh "${SSH_OPTS[@]}" "$TARGET" "cat > ${remote_path} <<'EOF'
${content}
EOF
chmod +x ${remote_path}
"
  echo "wrote ${remote_path}"
}

writeLocalUploadModelsScript() {
  local outPath="./uploadModels.sh"

  cat > "$outPath" <<'EOF'
#!/usr/bin/env bash
# uploadModels.sh (local)
#
# Upload minimal models required by fullbody_api.json
#
# Usage:
#   ./uploadModels.sh [--dry-run] [--model-root PATH] ssh user@host -p PORT -i KEY
#
# Defaults:
#   model-root = $HOME/Source/ComfyUI/models
#
# Example:
#   ./uploadModels.sh ssh root@213.192.2.88 -p 40190 -i ~/.ssh/id_ed25519
#   ./uploadModels.sh --model-root /mnt/myVideo/models ssh root@...

set -euo pipefail

DRY_RUN=0
DRY_PREFIX="[]"

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

if [[ "${1:-}" != "ssh" ]]; then
  echo "ERROR: expected ssh command"
  exit 1
fi
shift

TARGET=""
SSH_PORT="22"
SSH_IDENTITY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p) SSH_PORT="$2"; shift 2 ;;
    -i) SSH_IDENTITY="$2"; shift 2 ;;
    *)
      if [[ -z "$TARGET" ]]; then
        TARGET="$1"
        shift
      else
        echo "ERROR: unexpected arg: $1"
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: missing user@host"
  exit 1
fi

SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=accept-new)
if [[ -n "$SSH_IDENTITY" ]]; then
  SSH_OPTS+=(-i "$SSH_IDENTITY")
fi

echo "target   : ${TARGET}:${SSH_PORT}"
echo "identity : ${SSH_IDENTITY:-<default>}"
echo "dry run  : ${DRY_RUN}"
echo

# ============================================================
# REQUIRED FILES (from fullbody_api.json)
# ============================================================
CHECKPOINT="v1-5-pruned-emaonly.safetensors"
LORA="kathy_person_r16_512_bs2.safetensors"
YOLO="face_yolov8n.pt"

# ============================================================
# LOCAL MODEL ROOT
#
# Priority:
#   1) --model-root PATH
#   2) $HOME/Source/ComfyUI/models (default)
# ============================================================

if [[ -z "$MODEL_ROOT" ]]; then
  MODEL_ROOT="$HOME/Source/ComfyUI/models"
fi

if [[ ! -d "$MODEL_ROOT" ]]; then
  echo "ERROR: local models folder not found: $MODEL_ROOT"
  echo "       supply --model-root /path/to/models"
  exit 1
fi

# ============================================================
# REMOTE TARGET PATHS (fixed)
# ============================================================

REMOTE_BASE="/workspace/ComfyUI/models"
REMOTE_CHECKPOINT="${REMOTE_BASE}/checkpoints"
REMOTE_LORA="${REMOTE_BASE}/loras"
REMOTE_BBOX="${REMOTE_BASE}/bbox"

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "${DRY_PREFIX} $*"
  else
    "$@"
  fi
}

# Find a file in a preferred path first, then search under MODEL_ROOT.
findLocalFile() {
  local preferred="$1"
  local filename="$2"

  if [[ -f "$preferred" ]]; then
    echo "$preferred"
    return 0
  fi

  # fallback search (stop at first match)
  local found
  found="$(find "$MODEL_ROOT" -type f -name "$filename" -print -quit 2>/dev/null || true)"
  if [[ -n "$found" && -f "$found" ]]; then
    echo "$found"
    return 0
  fi

  return 1
}

# Preferred locations based on ComfyUI convention
LOCAL_CHECKPOINT="$(findLocalFile "${MODEL_ROOT}/checkpoints/${CHECKPOINT}" "${CHECKPOINT}")" || {
  echo "ERROR: could not find checkpoint: ${CHECKPOINT}"
  echo "       looked in: ${MODEL_ROOT}/checkpoints/"
  exit 1
}

LOCAL_LORA="$(findLocalFile "${MODEL_ROOT}/loras/${LORA}" "${LORA}")" || {
  echo "ERROR: could not find lora: ${LORA}"
  echo "       looked in: ${MODEL_ROOT}/loras/"
  exit 1
}

LOCAL_YOLO="$(findLocalFile "${MODEL_ROOT}/bbox/${YOLO}" "${YOLO}")" || {
  echo "ERROR: could not find yolo model: ${YOLO}"
  echo "       looked in: ${MODEL_ROOT}/bbox/"
  exit 1
}

echo "local model root : ${MODEL_ROOT}"
echo "checkpoint       : ${LOCAL_CHECKPOINT}"
echo "lora             : ${LOCAL_LORA}"
echo "bbox model       : ${LOCAL_YOLO}"
echo

# create remote dirs
run ssh "${SSH_OPTS[@]}" "$TARGET" \
  "mkdir -p '${REMOTE_CHECKPOINT}' '${REMOTE_LORA}' '${REMOTE_BBOX}'"

rsyncOne() {
  local src="$1"
  local dst="$2"

  run rsync -avP --partial --inplace \
    -e "ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY}" \
    "$src" "$TARGET:$dst/"
}

rsyncOne "$LOCAL_CHECKPOINT" "$REMOTE_CHECKPOINT"
rsyncOne "$LOCAL_LORA" "$REMOTE_LORA"
rsyncOne "$LOCAL_YOLO" "$REMOTE_BBOX"

echo
echo "done"
EOF

  chmod +x "$outPath"
  echo "wrote ${outPath}"
}



write_remote_file "/workspace/runpodSetup.sh" "$REMOTE_SETUP_SCRIPT"
write_remote_file "/workspace/runpodComfySetup.sh" "$REMOTE_COMFY_SETUP_SCRIPT"
write_remote_file "/workspace/startComfyUI.sh" "$REMOTE_COMFY_START_SCRIPT"
write_remote_file "/workspace/runpodKohyaSetup.sh" "$REMOTE_KOHYA_SETUP_SCRIPT"
writeLocalUploadModelsScript

echo

# ---------------------------
# Execute remote (or dry-run remote execution)
# ---------------------------
REMOTE_ARGS=()
if [[ "$ENABLE_KOHYA" == "1" ]]; then REMOTE_ARGS+=(--kohya); fi
if [[ "$ENABLE_COMFYUI" == "0" ]]; then REMOTE_ARGS+=(--no-comfyui); fi
if [[ "$RUN_REMOTE" == "0" ]]; then REMOTE_ARGS+=(--no-run); fi
if [[ "$DRY_RUN" == "1" ]]; then REMOTE_ARGS+=(--dry-run); fi

if [[ "$RUN_REMOTE" == "1" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[] would run on remote:"
    echo "[] ssh ${SSH_OPTS[*]} ${TARGET} 'bash /workspace/runpodSetup.sh ${REMOTE_ARGS[*]}'"
    exit 0
  fi

  echo "running remote setup:"
  ssh "${SSH_OPTS[@]}" "$TARGET" "bash /workspace/runpodSetup.sh ${REMOTE_ARGS[*]}"
else
  echo "remote scripts written. to run manually:"
  echo "  ssh -p ${SSH_PORT} ${TARGET} 'bash /workspace/runpodSetup.sh ${REMOTE_ARGS[*]}'"
fi
