#!/usr/bin/env bash
# steps/60_upload_models.sh
# Generate uploadModels.sh script for uploading models and workflows to RunPod (LOCAL step)
#
# Always regenerates uploadModels.sh (low overhead)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNPOD_TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="${RUNPOD_TOOLS_DIR}/lib"

# shellcheck disable=SC1091
source "${LIB_DIR}/common.sh"

main() {
  logTask "generating uploadModels.sh script"

  local outputFile="${RUNPOD_TOOLS_DIR}/uploadModels.sh"

  # Always regenerate
  cat > "$outputFile" <<'UPLOAD_SCRIPT'
#!/usr/bin/env bash
# uploadModels.sh (local)
#
# Upload minimal models and workflow files required by ComfyUI to RunPod
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

# Local model root
if [[ -z "$MODEL_ROOT" ]]; then
  MODEL_ROOT="$HOME/Source/ComfyUI/models"
fi

if [[ ! -d "$MODEL_ROOT" ]]; then
  echo "ERROR: local models folder not found: $MODEL_ROOT"
  echo "       supply --model-root /path/to/models"
  exit 1
fi

# Read workflow configuration from kohyaConfig.json
KOHYA_CONFIG="${KOHYA_CONFIG:-$HOME/.config/kohya/kohyaConfig.json}"

# Local workflows directory (from kohyaConfig.json)
WORKFLOWS_DIR=""
if [[ -f "$KOHYA_CONFIG" ]] && command -v python3 &>/dev/null; then
  WORKFLOWS_DIR="$(python3 - "$KOHYA_CONFIG" <<'PY'
import json, sys, os
p=sys.argv[1]
try:
    with open(p,'r') as f:
        cfg=json.load(f)
except Exception:
    sys.exit(0)

# Prefer explicit key, but accept older key names too
val = (
    cfg.get('workflowsDir')
    or cfg.get('comfyWorkflowsDir')
    or ''
)
if isinstance(val,str) and val.strip():
    print(os.path.expanduser(val.strip()))
PY
)"
fi

# Fallback
if [[ -z "$WORKFLOWS_DIR" ]]; then
  WORKFLOWS_DIR="$HOME/Source/ComfyUI/user/default/workflows_api"
fi

# Expand home directory reference
WORKFLOWS_DIR="${WORKFLOWS_DIR/#\~/$HOME}"


# Remote target paths
REMOTE_BASE="/workspace/ComfyUI/models"
REMOTE_CHECKPOINT="${REMOTE_BASE}/checkpoints"
REMOTE_LORA="${REMOTE_BASE}/loras"
REMOTE_BBOX="${REMOTE_BASE}/ultralytics/bbox"
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

# Workflows directory (sync all files)
WORKFLOW_COUNT=0
if [[ -d "$WORKFLOWS_DIR" ]]; then
  WORKFLOW_COUNT="$(find "$WORKFLOWS_DIR" -maxdepth 1 -type f 2>/dev/null | wc -l | tr -d ' ')"
fi


echo
echo "=== Models ==="
echo "local model root : ${MODEL_ROOT}"
echo "checkpoint       : ${LOCAL_CHECKPOINT}"
echo "lora             : ${LOCAL_LORA}"
echo "bbox model       : ${LOCAL_YOLO}"
echo

echo "=== Workflows ==="
if [[ -d "$WORKFLOWS_DIR" ]]; then
  echo "local workflows dir: ${WORKFLOWS_DIR}"
  echo "workflow files found: ${WORKFLOW_COUNT}"
  if [[ "${WORKFLOW_COUNT}" -gt 0 ]]; then
    while IFS= read -r f; do
      echo "  - $f"
    done < <(find "$WORKFLOWS_DIR" -maxdepth 1 -type f -printf "%f
" 2>/dev/null | sort)
  else
    echo "WARNING: workflows directory exists but contains no files"
  fi
else
  echo "WARNING: workflows directory not found: ${WORKFLOWS_DIR}"
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

# Upload workflows directory (all files)
if [[ -d "$WORKFLOWS_DIR" && "${WORKFLOW_COUNT}" -gt 0 ]]; then
  echo
  echo "=== Uploading Workflows ==="
  run rsync -avP --partial --inplace --no-perms --no-owner --no-group     -e "ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY}"     "${WORKFLOWS_DIR}/" "$TARGET:${REMOTE_WORKFLOWS}/"
fi

echo
echo "done"
UPLOAD_SCRIPT

  chmod +x "$outputFile" || true
  log "uploadModels.sh created at: $outputFile"
  log "done\n"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
