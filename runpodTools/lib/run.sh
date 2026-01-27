# run.sh

DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="${DRY_PREFIX:-[]}"

# New: central way to detect if we're simulating locally
isLocalMode() {
  [[ "${LOCAL_MODE:-0}" == "1" ]] || [[ "${SSH_TARGET:-}" == "local" ]]
}

dryrun() {
  echo "${DRY_PREFIX:-...[]} $*"
}

run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$*"
    return 0
  fi

  if isLocalMode; then
    bash -c "$*"
  else
    runRemote "$@"
  fi
}

runCapture() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    # For dry-run we could echo something, but simplest is to return empty
    echo "(dry-run capture)"
    return 0
  fi

  if isLocalMode; then
    bash -c "$*" 2>&1
  else
    runRemoteCapture "$*"
  fi
}

runLocal() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$*"
    return 0
  fi
  # Always truly local — no change needed
  "$@"
}