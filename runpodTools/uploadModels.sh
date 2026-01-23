#!/usr/bin/env bash
# uploadModels.sh (local)
#
# Upload minimal models and workflow files required by ComfyUI to RunPod
#
# Usage:
#   ./uploadModels.sh [--dry-run] [--model-root PATH] [--workflows-dir PATH] ssh user@host -p PORT -i KEY
#
# Defaults:
#   model-root = $HOME/Source/ComfyUI/models
#   workflows-dir = ~/.config/kohya/workflows (from kohyaConfig.json)
#
# Example:
#   ./uploadModels.sh ssh root@213.192.2.88 -p 40190 -i ~/.ssh/id_ed25519
#   ./uploadModels.sh --model-root /mnt/myVideo/models ssh root@...

set -euo pipefail

DRY_RUN=0
DRY_PREFIX="[]"
MODEL_ROOT=""
WORKFLOWS_DIR=""

usage() {
  sed -n '2,15p' "$0"
  exit 0
}

# Parse options before ssh command
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage ;;
    --dry-run) DRY_RUN=1; shift ;;
    --model-root)
      if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        echo "ERROR: --model-root requires a PATH argument"
        exit 1
      fi
      MODEL_ROOT="$2"
      shift 2
      ;;
    --workflows-dir)
      if [[ -z "${2:-}" || "${2:-}" == -* ]]; then
        echo "ERROR: --workflows-dir requires a PATH argument"
        exit 1
      fi
      WORKFLOWS_DIR="$2"
      shift 2
      ;;
    ssh) shift; break ;;
    *)
      echo "ERROR: unexpected option: $1"
      echo "Run with --help for usage information"
      exit 1
      ;;
  esac
done

TARGET=""
SSH_PORT="22"
SSH_IDENTITY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p)
      if [[ -z "${2:-}" ]]; then
        echo "ERROR: -p requires a port number"
        exit 1
      fi
      SSH_PORT="$2"
      shift 2
      ;;
    -i)
      if [[ -z "${2:-}" ]]; then
        echo "ERROR: -i requires an identity file path"
        exit 1
      fi
      SSH_IDENTITY="$2"
      shift 2
      ;;
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

# Required model files (from fullbody_api.json)
CHECKPOINT="v1-5-pruned-emaonly.safetensors"
LORA="kathy_person_r16_512_bs2.safetensors"
YOLO="face_yolov8n.pt"

# Required workflow files
WORKFLOW_FILES=(
  "fullbody_api.json"
  "halfbody_api.json"
  "portrait_api.json"
)

# Local model root
if [[ -z "$MODEL_ROOT" ]]; then
  MODEL_ROOT="$HOME/Source/ComfyUI/models"
fi

if [[ ! -d "$MODEL_ROOT" ]]; then
  echo "ERROR: local models folder not found: $MODEL_ROOT"
  echo "       supply --model-root /path/to/models"
  exit 1
fi

# Local workflows directory
if [[ -z "$WORKFLOWS_DIR" ]]; then
  # Try to read from kohyaConfig.json if available
  KOHYA_CONFIG="$HOME/.config/kohya/kohyaConfig.json"
  if [[ -f "$KOHYA_CONFIG" ]] && command -v python3 &>/dev/null; then
    WORKFLOWS_DIR=$(python3 -c "
import json, sys
try:
    with open(sys.argv[1], 'r') as f:
        cfg = json.load(f)
        print(cfg.get('comfyWorkflowsDir', ''))
except:
    pass
" "$KOHYA_CONFIG" 2>/dev/null || true)
  fi
  
  # Fallback to default if not found
  if [[ -z "$WORKFLOWS_DIR" ]]; then
    WORKFLOWS_DIR="$HOME/.config/kohya/workflows"
  fi
fi

# Expand home directory reference
WORKFLOWS_DIR="${WORKFLOWS_DIR/#\~/$HOME}"

# Remote target paths
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

# Find required model files
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

# Find and validate workflow files
declare -a LOCAL_WORKFLOW_PATHS=()
declare -a MISSING_WORKFLOWS=()

if [[ -d "$WORKFLOWS_DIR" ]]; then
  for workflow in "${WORKFLOW_FILES[@]}"; do
    workflow_path="${WORKFLOWS_DIR}/${workflow}"
    if [[ -f "$workflow_path" ]]; then
      LOCAL_WORKFLOW_PATHS+=("$workflow_path")
    else
      MISSING_WORKFLOWS+=("$workflow")
    fi
  done
fi

echo
echo "=== Models ==="
echo "local model root : ${MODEL_ROOT}"
echo "checkpoint       : ${LOCAL_CHECKPOINT}"
echo "lora             : ${LOCAL_LORA}"
echo "bbox model       : ${LOCAL_YOLO}"
echo

echo "=== Workflows ==="
if [[ ${#LOCAL_WORKFLOW_PATHS[@]} -gt 0 ]]; then
  echo "local workflows dir: ${WORKFLOWS_DIR}"
  echo "workflow files found: ${#LOCAL_WORKFLOW_PATHS[@]}"
  for path in "${LOCAL_WORKFLOW_PATHS[@]}"; do
    echo "  - $(basename "$path")"
  done
elif [[ -d "$WORKFLOWS_DIR" ]]; then
  echo "WARNING: workflows directory exists but no workflow files found"
  echo "         looked in: ${WORKFLOWS_DIR}"
  for missing in "${MISSING_WORKFLOWS[@]}"; do
    echo "  - missing: $missing"
  done
else
  echo "WARNING: workflows directory not found: ${WORKFLOWS_DIR}"
  echo "         use --workflows-dir to specify location"
fi
echo

# Create remote dirs
run ssh "${SSH_OPTS[@]}" "$TARGET" \
  "mkdir -p '${REMOTE_CHECKPOINT}' '${REMOTE_LORA}' '${REMOTE_BBOX}' '${REMOTE_WORKFLOWS}'"

rsyncOne() {
  local src="$1"
  local dst="$2"

  run rsync -avP --partial --inplace --no-perms --no-owner --no-group \
    -e "ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY}" \
    "$src" "$TARGET:$dst/"
}

# Upload model files
echo "=== Uploading Models ==="
rsyncOne "$LOCAL_CHECKPOINT" "$REMOTE_CHECKPOINT"
rsyncOne "$LOCAL_LORA" "$REMOTE_LORA"
rsyncOne "$LOCAL_YOLO" "$REMOTE_BBOX"

# Upload workflow files if found
if [[ ${#LOCAL_WORKFLOW_PATHS[@]} -gt 0 ]]; then
  echo
  echo "=== Uploading Workflows ==="
  for workflow_path in "${LOCAL_WORKFLOW_PATHS[@]}"; do
    rsyncOne "$workflow_path" "$REMOTE_WORKFLOWS"
  done
fi

echo
echo "done"
