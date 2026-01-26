# run.sh

DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="${DRY_PREFIX:-[]}"

dryrun() {
  echo "${DRY_PREFIX:-...[]} $*"
}

run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$*"
    return 0
  fi
  runRemote "$@"
}

runCapture() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    return 0
  fi
  runRemoteCapture "$*"
}

runLocal() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    dryrun "$*"
    return 0
  fi
  "$@"
}
