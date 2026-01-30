#!/usr/bin/env bash
# steps/10_diagnostics.sh
# Run system diagnostics

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/diagnostics.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  # Check if already done and not forcing
  if isStepDone "DIAGNOSTICS" && [[ "${FORCE:-0}" != "1" ]]; then
    log "diagnostics already completed (use --force to rerun)"
    return 0
  fi
  
  logTask "running runpod diagnostics"
  runDiagnostics
  
  markStepDone "DIAGNOSTICS"
  markStepDone "GPU_CHECK"
  log "diagnostics done\n"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
