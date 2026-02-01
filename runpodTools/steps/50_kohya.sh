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

  # Check if already done and not forcing
  if isStepDone "KOHYA" && [[ "${FORCE:-0}" != "1" ]]; then
    log "kohya already configured (use --force to rerun)"
    return 0
  fi

  # Ensure repo (remote-safe ensureGitRepo required)
  if ! isStepDone "KOHYA_REPO"; then
    log "ensuring kohya repo"
    ensureGitRepo "$KOHYA_DIR" "https://github.com/bmaltais/kohya_ss.git" "kohya_ss"
    markStepDone "KOHYA_REPO"
  else
    log "kohya repository already cloned"
  fi

  # Ensure submodules
  if ! isStepDone "KOHYA_SUBMODULES"; then
    log "ensuring kohya submodules"
    runCmd git -C "${KOHYA_DIR}" submodule sync --recursive
    runCmd git -C "${KOHYA_DIR}" submodule update --init --recursive --force

    if [[ ! -f "${KOHYA_DIR}/sd-scripts/pyproject.toml" && ! -f "${KOHYA_DIR}/sd-scripts/setup.py" ]]; then
      error "sd-scripts submodule not initialized correctly: ${KOHYA_DIR}/sd-scripts"
      return 1
    fi
    markStepDone "KOHYA_SUBMODULES"
  else
    log "kohya submodules already initialized"
  fi

  # Install dependencies
  if ! isStepDone "KOHYA_REQUIREMENTS"; then
    log "installing kohya_ss dependencies"
    condaEnvSh "$ENV_NAME" "cd '$KOHYA_DIR' && python -m pip install --root-user-action=ignore -r requirements.txt"
    markStepDone "KOHYA_REQUIREMENTS"
  else
    log "kohya requirements already installed"
  fi

  markStepDone "KOHYA"
  log "kohya done\n"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
