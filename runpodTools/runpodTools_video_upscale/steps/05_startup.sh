set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/conda.sh"

main() {
  # In the case where a pod is restarted we loose the /root folder so need a quick way to create it again

  # Create bash aliases
  log "creating /root/.bash_aliases"
  runSh "echo \"alias d='ls -al'\" >> ~/.bash_aliases"

  # here we want to run "conda init"
  if ! ensureCondaInitBash ; then
    log "conda init failed, but continuing anyway"
  fi
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
