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

  log "ensuring kohya submodules"
  runCmd git -C "${KOHYA_DIR}" submodule sync --recursive
  runCmd git -C "${KOHYA_DIR}" submodule update --init --recursive --force

  if [[ ! -f "${KOHYA_DIR}/sd-scripts/pyproject.toml" && ! -f "${KOHYA_DIR}/sd-scripts/setup.py" ]]; then
    error "sd-scripts submodule not initialized correctly: ${KOHYA_DIR}/sd-scripts"
    return 1
  fi

  log "installing kohya_ss dependencies"
  condaRunCmd "$ENV_NAME" python -m pip install --root-user-action=ignore -r "$KOHYA_DIR/sd-scripts/requirements.txt"

  markStepDone "KOHYA"
  log "kohya done\n"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
