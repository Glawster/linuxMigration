#!/usr/bin/env bash
# steps/60_upload_models.sh
# Generate uploadModels.sh script for model uploads

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"
RUNPOD_TOOLS_DIR="$(dirname "$SCRIPT_DIR")"

# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  log "step: upload models"
  
  log "generating uploadModels.sh script"
  
  # Generate the upload script
  local GENERATE_SCRIPT="${RUNPOD_TOOLS_DIR}/generateUploadScript.sh"
  local OUTPUT_FILE="${RUNPOD_TOOLS_DIR}/uploadModels.sh"
  
  if [[ -f "$GENERATE_SCRIPT" ]]; then
    "$GENERATE_SCRIPT" "$OUTPUT_FILE"
    log "uploadModels.sh created at: $OUTPUT_FILE"
    
    cat <<'INFO'

To upload models to this RunPod instance, run:
   ./runpodTools/uploadModels.sh ssh user@host -p PORT -i KEY

For ComfyUI, ensure you have these model types:
- checkpoints (in models/checkpoints/)
- loras (in models/loras/)
- bbox models (in models/bbox/)
INFO
  else
    warn "generateUploadScript.sh not found at: $GENERATE_SCRIPT"
  fi
  
  log "upload models step complete"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
