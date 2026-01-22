#!/usr/bin/env bash
# steps/60_upload_models.sh
# Generate uploadModels.sh script for model uploads

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"
RUNPOD_TOOLS_DIR="$(dirname "$SCRIPT_DIR")"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  logTask "generating uploadModels.sh script"
  
  # Generate the upload script in the LOCAL runpodTools directory
  local GENERATE_SCRIPT="${RUNPOD_TOOLS_DIR}/generateUploadScript.sh"
  local OUTPUT_FILE="${RUNPOD_TOOLS_DIR}/uploadModels.sh"
  
  if [[ -f "$GENERATE_SCRIPT" ]]; then
    # Run the generator directly (it should already be local)
    bash "$GENERATE_SCRIPT" "$OUTPUT_FILE"
    
    if [[ -f "$OUTPUT_FILE" ]]; then
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
      warn "uploadModels.sh was not created successfully"
    fi
  else
    warn "generateUploadScript.sh not found at: $GENERATE_SCRIPT"
  fi
  
  log "upload models step complete"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
