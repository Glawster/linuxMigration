#!/usr/bin/env bash
# steps/50_kohya.sh
# Setup Kohya SS

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/git.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

main() {
  logTask "kohya"
  
  # Check if already done and not forcing
  if isStepDone "KOHYA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "kohya already configured (use --force to rerun)"
    return 0
  fi
  
  # Ensure repo
  ensureGitRepo "$KOHYA_DIR" "https://github.com/bmaltais/kohya_ss.git"
  
  # Activate conda
  activateCondaEnv "$CONDA_DIR" "$ENV_NAME"
  
  # Install dependencies
  log "installing kohya_ss dependencies"
  
  run bash -c '
    if [[ -f "$KOHYA_DIR/requirements.txt" ]]; then
      pip install -r "$KOHYA_DIR/requirements.txt"
    fi
  '

  markStepDone "KOHYA"
  log "kohya done"
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
