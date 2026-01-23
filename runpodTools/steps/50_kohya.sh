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

  # Ensure repo (remote-safe ensureGitRepo required)
  ensureGitRepo "$KOHYA_DIR" "https://github.com/bmaltais/kohya_ss.git"

  log "installing kohya_ss dependencies"

  # ensure sd-scripts exists where kohya expects it
  if ! run test -d "$KOHYA_DIR/sd-scripts"; then
    log "cloning sd-scripts into kohya_ss"
    ensureGitRepo "$KOHYA_DIR/sd-scripts" "https://github.com/kohya-ss/sd-scripts.git"
  fi

  log "installing kohya_ss dependencies"

  # IMPORTANT: requirements.txt existence must be checked REMOTELY
  if run test -f "$KOHYA_DIR/requirements.txt"; then
    condaEnvRun "$ENV_NAME" bash -lc "cd '$KOHYA_DIR' && python -m pip install -r requirements.txt --root-user-action=ignore"
  else
    warn "requirements.txt not found: $KOHYA_DIR/requirements.txt"
  fi

  markStepDone "KOHYA"
  log "kohya done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
