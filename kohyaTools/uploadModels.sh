#!/usr/bin/env bash
# uploadModels.sh (local)
#
# Upload minimal models required by fullbody_api.json and workflow files
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
# READ WORKFLOW CONFIG
# ============================================================

CONFIG_FILE="$HOME/.config/kohya/kohyaConfig.json"
WORKFLOW_FILE=""
WORKFLOW_DIR=""
LOCAL_WORKFLOW=""

if [[ -f "$CONFIG_FILE" ]]; then
  echo "reading workflow config from: $CONFIG_FILE"
  
  # Read workflow file name and directory from config using python
  if command -v python3 >/dev/null 2>&1; then
    WORKFLOW_FILE=$(python3 -c "import json; cfg=json.load(open('$CONFIG_FILE')); print(cfg.get('comfyFullbodyWorkflow', ''))" 2>/dev/null || echo "")
    WORKFLOW_DIR=$(python3 -c "import json; cfg=json.load(open('$CONFIG_FILE')); print(cfg.get('comfyWorkflowsDir', ''))" 2>/dev/null || echo "")
    
    if [[ -n "$WORKFLOW_FILE" && -n "$WORKFLOW_DIR" ]]; then
      LOCAL_WORKFLOW="$WORKFLOW_DIR/$WORKFLOW_FILE"
      if [[ -f "$LOCAL_WORKFLOW" ]]; then
        echo "workflow file    : $LOCAL_WORKFLOW"
      else
        echo "WARNING: workflow file not found: $LOCAL_WORKFLOW"
        LOCAL_WORKFLOW=""
      fi
    else
      echo "INFO: workflow config not found in config file (comfyFullbodyWorkflow or comfyWorkflowsDir missing)"
    fi
  else
    echo "WARNING: python3 not available, cannot read workflow config"
  fi
else
  echo "INFO: config file not found: $CONFIG_FILE"
fi

# ============================================================
# REMOTE TARGET PATHS (fixed)
# ============================================================

REMOTE_BASE="/workspace/ComfyUI/models"
REMOTE_CHECKPOINT="${REMOTE_BASE}/checkpoints"
REMOTE_LORA="${REMOTE_BASE}/loras"
REMOTE_BBOX="${REMOTE_BASE}/bbox"
REMOTE_WORKFLOWS="/workspace/workflows"

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

echo
echo "local model root : ${MODEL_ROOT}"
echo "checkpoint       : ${LOCAL_CHECKPOINT}"
echo "lora             : ${LOCAL_LORA}"
echo "bbox model       : ${LOCAL_YOLO}"
echo

# create remote dirs
run ssh "${SSH_OPTS[@]}" "$TARGET" \
  "mkdir -p '${REMOTE_CHECKPOINT}' '${REMOTE_LORA}' '${REMOTE_BBOX}' '${REMOTE_WORKFLOWS}'"

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

# Upload workflow file if found
if [[ -n "$LOCAL_WORKFLOW" && -f "$LOCAL_WORKFLOW" ]]; then
  echo
  echo "uploading workflow file..."
  rsyncOne "$LOCAL_WORKFLOW" "$REMOTE_WORKFLOWS"
fi

echo
echo "done"
