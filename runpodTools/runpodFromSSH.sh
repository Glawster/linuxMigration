#!/usr/bin/env bash
# runpodFromSSH.sh (modular version)
#
# Local helper that:
# - Parses SSH connection details
# - Copies the runpod/ folder to the remote host
# - Executes the remote bootstrap script
#
# Usage:
#   ./runpodFromSSH.sh [options] ssh user@host -p PORT -i KEY
#
# Options:
#   --kohya          enable kohya setup
#   --no-comfyui     disable comfyui setup
#   --no-run         only copy files, don't execute bootstrap
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
RUNPOD_DIR="$SCRIPT_DIR/runpodTools"

ENABLE_KOHYA=0
ENABLE_COMFYUI=1
RUN_REMOTE=1
DRY_RUN=0
FORCE=0
FROM_STEP=""
ONLY_STEP=""
SKIP_STEPS=()
LIST_STEPS=0

usage() {
  sed -n '2,25p' "$0"
  exit 0
}

# Parse options before ssh command
while [[ $# -gt 0 ]]; do
  case "$1" in
    --kohya) ENABLE_KOHYA=1; shift ;;
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;
    --no-run) RUN_REMOTE=0; shift ;;
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
echo "run remote  : ${RUN_REMOTE}"
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

# Install base tools first (includes rsync)
echo "installing base tools on remote..."

if [[ "$DRY_RUN" == "1" ]]; then
  echo "...[] would install base tools"
else
  # Run apt-get update and install essential packages including rsync
  ssh "${SSH_OPTS[@]}" "$TARGET" 'bash -s' <<'INSTALL_BASE_TOOLS'
set -euo pipefail

# Set environment for non-interactive apt
export DEBIAN_FRONTEND=noninteractive
export TZ=Etc/UTC
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

echo "...updating apt"
apt-get update -y >/dev/null 2>&1

echo "...installing base packages"
apt-get install -y \
  git \
  wget \
  rsync \
  tmux \
  htop \
  unzip \
  build-essential \
  python3-venv \
  python3-pip \
  ca-certificates \
  vim >/dev/null 2>&1

echo "...base tools installed"
INSTALL_BASE_TOOLS
fi
echo

# Copy runpod folder to remote (rsync is now available)
echo "copying runpodTools/ to remote..."

if [[ "$DRY_RUN" == "1" ]]; then
  echo "...[] would rsync $RUNPOD_DIR to ${TARGET}:/workspace/runpodTools/"
else
  # Use rsync (now installed on remote)
  if command -v rsync >/dev/null 2>&1; then
    rsync -avz --delete \
      -e "ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY}" \
      "$RUNPOD_DIR/" "$TARGET:/workspace/runpodTools/"
    echo "...rsync complete"
  else
    # Fallback if rsync not on local (unlikely)
    echo "...using tar+ssh (rsync not available locally)"
    tar czf - -C "$(dirname "$RUNPOD_DIR")" runpodTools | \
      ssh "${SSH_OPTS[@]}" "$TARGET" "cd /workspace && tar xzf -"
    echo "...tar transfer complete"
  fi
fi
echo

# Handle --list (run remote list and exit)
if [[ "$LIST_STEPS" == "1" ]]; then
  echo "available steps on remote:"
  # shellcheck disable=SC2029
  ssh "${SSH_OPTS[@]}" "$TARGET" "bash /workspace/runpodTools/runpodBootstrap.sh --list"
  exit 0
fi

# Build remote arguments
REMOTE_ARGS=()
if [[ "$ENABLE_KOHYA" == "1" ]]; then
  REMOTE_ARGS+=(--kohya)
fi
if [[ "$ENABLE_COMFYUI" == "0" ]]; then
  REMOTE_ARGS+=(--no-comfyui)
fi
if [[ "$DRY_RUN" == "1" ]]; then
  REMOTE_ARGS+=(--dry-run)
fi
if [[ "$FORCE" == "1" ]]; then
  REMOTE_ARGS+=(--force)
fi
if [[ -n "$FROM_STEP" ]]; then
  REMOTE_ARGS+=(--from "$FROM_STEP")
fi
if [[ -n "$ONLY_STEP" ]]; then
  REMOTE_ARGS+=(--only "$ONLY_STEP")
fi
# Skip base_tools since we already installed it
REMOTE_ARGS+=(--skip "20_base_tools")
for skip_step in "${SKIP_STEPS[@]}"; do
  REMOTE_ARGS+=(--skip "$skip_step")
done

# Execute remote bootstrap
if [[ "$RUN_REMOTE" == "1" ]]; then
  echo "running remote bootstrap..."
  
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "...[] would run: ssh ${SSH_OPTS[*]} ${TARGET} bash /workspace/runpodTools/runpodBootstrap.sh ${REMOTE_ARGS[*]}"
  else
    # shellcheck disable=SC2029
    ssh "${SSH_OPTS[@]}" "$TARGET" "bash /workspace/runpodTools/runpodBootstrap.sh ${REMOTE_ARGS[*]}"
  fi
else
  echo "remote scripts copied. to run manually:"
  echo "  ssh -p ${SSH_PORT} ${SSH_IDENTITY:+-i $SSH_IDENTITY} ${TARGET}"
  echo "  bash /workspace/runpodTools/runpodBootstrap.sh ${REMOTE_ARGS[*]}"
fi
