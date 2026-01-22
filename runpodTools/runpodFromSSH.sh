#!/usr/bin/env bash
# runpodFromSSH.sh (modular version)
#
# Local orchestrator that:
# - Parses SSH connection details
# - Executes all commands on remote via SSH from local
# - No files copied to remote (all scripts stay local)
#
# Usage:
#   ./runpodFromSSH.sh [options] ssh user@host -p PORT -i KEY
#
# Options:
#   --kohya          enable kohya setup
#   --no-comfyui     disable comfyui setup
#   --dry-run        dry run mode (show what would be done)
#   --force          force rerun of all steps
#   --from STEP      start from specific step
#   --only STEP      run only specific step
#   --skip STEP      skip specific step
#   --list           list available steps
#   -h, --help       show this help
#
# Example:
#   ./runpodFromSSH.sh ssh root@213.192.2.88 -p 40023 -i ~/.ssh/id_ed25519
#   ./runpodFromSSH.sh --kohya ssh root@...
#   ./runpodFromSSH.sh --only 40_comfyui ssh root@...

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DRY_RUN=0
DRY_PREFIX="[]"

BOOTSTRAP_ARGS=()

# parse options until we hit "ssh"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      BOOTSTRAP_ARGS+=(--dry-run)
      shift
      ;;
    --kohya)
      BOOTSTRAP_ARGS+=(--kohya)
      shift
      ;;
    --no-comfyui)
      BOOTSTRAP_ARGS+=(--no-comfyui)
      shift
      ;;
    --force)
      BOOTSTRAP_ARGS+=(--force)
      shift
      ;;
    --from|--only|--skip)
      BOOTSTRAP_ARGS+=("$1" "$2")
      shift 2
      ;;
    --list|-h|--help)
      BOOTSTRAP_ARGS+=("$1")
      shift
      ;;
    ssh)
      shift
      break
      ;;
    *)
      usage
      ;;
  esac
done

SSH_TARGET=""
SSH_PORT=""
SSH_IDENTITY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p)
      SSH_PORT="$2"
      shift 2
      ;;
    -i)
      SSH_IDENTITY="$2"
      shift 2
      ;;
    *)
      if [[ -z "$SSH_TARGET" ]]; then
        SSH_TARGET="$1"
        shift
      else
        echo "ERROR: unexpected arg: $1" >&2
        exit 1
      fi
      ;;
  esac
done

if [[ -z "$SSH_TARGET" ]]; then
  echo "ERROR: missing user@host" >&2
  exit 1
fi

echo "target      : ${SSH_TARGET}${SSH_PORT:+:${SSH_PORT}}"
echo "identity    : ${SSH_IDENTITY:-<default>}"
echo "dry run     : ${DRY_RUN}"
echo

# export remote mode so common.sh refuses local execution
export REQUIRE_REMOTE=1
export DRY_RUN
export DRY_PREFIX

export SSH_TARGET
export SSH_PORT
export SSH_IDENTITY

# quick connectivity check (real even in dry-run; cheap + catches wrong port)
echo "checking ssh connectivity..."
if [[ "${DRY_RUN}" == "1" ]]; then
  echo "${DRY_PREFIX} ssh -p ${SSH_PORT} -o StrictHostKeyChecking=accept-new ${SSH_IDENTITY:+-i ${SSH_IDENTITY}} ${SSH_TARGET} 'echo connected && uname -a'"
else
  ssh -p "${SSH_PORT}" -o StrictHostKeyChecking=accept-new ${SSH_IDENTITY:+-i "${SSH_IDENTITY}"} \
    "${SSH_TARGET}" "echo connected && uname -a" >/dev/null
  echo "connected..."
fi
echo

# run modular bootstrap (steps must use run/isCommand only)
exec bash "${SCRIPT_DIR}/runpodBootstrap.sh" "${BOOTSTRAP_ARGS[@]}"
