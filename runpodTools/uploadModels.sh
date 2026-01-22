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
MODEL_ROOT=""

usage() {
  sed -n '2,14p' "$0"
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

# Required files (from fullbody_api.json)
CHECKPOINT="v1-5-pruned-emaonly.safetensors"
LORA="kathy_person_r16_512_bs2.safetensors"
YOLO="face_yolov8n.pt"

# Local model root
if [[ -z "$MODEL_ROOT" ]]; then
  MODEL_ROOT="$HOME/Source/ComfyUI/models"
fi

if [[ ! -d "$MODEL_ROOT" ]]; then
  echo "ERROR: local models folder not found: $MODEL_ROOT"
  echo "       supply --model-root /path/to/models"
  exit 1
fi

# Remote target paths
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

# Find required files
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

# Create remote dirs
run ssh "${SSH_OPTS[@]}" "$TARGET" \
  "mkdir -p '${REMOTE_CHECKPOINT}' '${REMOTE_LORA}' '${REMOTE_BBOX}'"

rsyncOne() {
  local src="$1"
  local dst="$2"

  run rsync -avP --partial --inplace --no-perms --no-owner --no-group \
    -e "ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY}" \
    "$src" "$TARGET:$dst/"
}

rsyncOne "$LOCAL_CHECKPOINT" "$REMOTE_CHECKPOINT"
rsyncOne "$LOCAL_LORA" "$REMOTE_LORA"
rsyncOne "$LOCAL_YOLO" "$REMOTE_BBOX"

echo
echo "done"
