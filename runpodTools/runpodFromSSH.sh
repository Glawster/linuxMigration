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
RUNPOD_DIR="$SCRIPT_DIR"

ENABLE_KOHYA=0
ENABLE_COMFYUI=1
DRY_RUN=0
FORCE=0
FROM_STEP=""
ONLY_STEP=""
SKIP_STEPS=()
LIST_STEPS=0

usage() {
  sed -n '2,23p' "$0"
  exit 0
}

# Parse options before ssh command
while [[ $# -gt 0 ]]; do
  case "$1" in
    --kohya) ENABLE_KOHYA=1; shift ;;
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force) FORCE=1; shift ;;
    --from)
      FROM_STEP="$2"
      shift 2
      ;;
    --only)
      ONLY_STEP="$2"
      shift 2
      ;;
    --skip)
      SKIP_STEPS+=("$2")
      shift 2
      ;;
    --list) LIST_STEPS=1; shift ;;
    -h|--help) usage ;;
    ssh) break ;;
    *)
      echo "ERROR: unknown option: $1"
      usage
      ;;
  esac
done

if [[ $# -lt 2 || "$1" != "ssh" ]]; then
  echo "ERROR: expected ssh command after options"
  usage
fi
shift

# Parse SSH arguments
TARGET=""
SSH_PORT="22"
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
      if [[ -z "$TARGET" ]]; then
        TARGET="$1"
      else
        echo "ERROR: unexpected argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$TARGET" ]]; then
  echo "ERROR: could not determine user@host"
  exit 1
fi

# Build SSH options
SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=accept-new)
if [[ -n "$SSH_IDENTITY" ]]; then
  SSH_OPTS+=(-i "$SSH_IDENTITY")
fi

echo "target      : ${TARGET}:${SSH_PORT}"
echo "identity    : ${SSH_IDENTITY:-<default>}"
echo "comfyui     : ${ENABLE_COMFYUI}"
echo "kohya       : ${ENABLE_KOHYA}"
echo "dry run     : ${DRY_RUN}"
echo "force       : ${FORCE}"
if [[ -n "$FROM_STEP" ]]; then
  echo "from step   : ${FROM_STEP}"
fi
if [[ -n "$ONLY_STEP" ]]; then
  echo "only step   : ${ONLY_STEP}"
fi
if [[ ${#SKIP_STEPS[@]} -gt 0 ]]; then
  echo "skip steps  : ${SKIP_STEPS[*]}"
fi
if [[ "$LIST_STEPS" == "1" ]]; then
  echo "list steps  : yes"
fi
echo

# Check connectivity
echo "checking ssh connectivity..."
if ssh "${SSH_OPTS[@]}" "$TARGET" "echo connected && uname -a" >/dev/null 2>&1; then
  echo "...connected"
else
  echo "ERROR: could not connect to ${TARGET}:${SSH_PORT}"
  exit 1
fi
echo

# Handle --list 
if [[ "$LIST_STEPS" == "1" ]]; then
  # Run local runpodBootstrap.sh to list steps
  "$RUNPOD_DIR/runpodBootstrap.sh" --list
  exit 0
fi

# Build bootstrap arguments for local execution
BOOTSTRAP_ARGS=()
if [[ "$ENABLE_KOHYA" == "1" ]]; then
  BOOTSTRAP_ARGS+=(--kohya)
fi
if [[ "$ENABLE_COMFYUI" == "0" ]]; then
  BOOTSTRAP_ARGS+=(--no-comfyui)
fi
if [[ "$DRY_RUN" == "1" ]]; then
  BOOTSTRAP_ARGS+=(--dry-run)
fi
if [[ "$FORCE" == "1" ]]; then
  BOOTSTRAP_ARGS+=(--force)
fi
if [[ -n "$FROM_STEP" ]]; then
  BOOTSTRAP_ARGS+=(--from "$FROM_STEP")
fi
if [[ -n "$ONLY_STEP" ]]; then
  BOOTSTRAP_ARGS+=(--only "$ONLY_STEP")
fi
for skip_step in "${SKIP_STEPS[@]}"; do
  BOOTSTRAP_ARGS+=(--skip "$skip_step")
done

# Export SSH connection details for steps to use
export SSH_TARGET="$TARGET"
export SSH_PORT
export SSH_IDENTITY
export SSH_OPTS_STR="${SSH_OPTS[*]}"

# Run runpodBootstrap.sh LOCALLY (it will SSH to remote for each command)
echo "running bootstrap locally (executing commands on remote via SSH)..."
"$RUNPOD_DIR/runpodBootstrap.sh" "${BOOTSTRAP_ARGS[@]}"
