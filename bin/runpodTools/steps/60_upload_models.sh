#!/usr/bin/env bash
# steps/60_upload_models.sh
# Instructions for uploading models (informational step)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  log "==> step: upload models"
  
  log "...model upload instructions"
  
  cat <<'INFO'

To upload models to this RunPod instance:

1. Generate the uploadModels.sh script locally:
   ./runpodBootstrap.sh --upload

2. Run the upload script with your connection details:
   ./uploadModels.sh ssh user@host -p PORT -i KEY

3. Or use rsync directly:
   rsync -avP --partial --inplace --ignore-existing \
     -e "ssh -p PORT -i ~/.ssh/KEY" \
     models/ user@host:/workspace/ComfyUI/models/

For ComfyUI, ensure you have these model types:
- checkpoints (in models/checkpoints/)
- loras (in models/loras/)
- bbox models (in models/bbox/)

INFO
  
  log "...upload models info displayed"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
