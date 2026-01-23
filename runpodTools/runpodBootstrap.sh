#!/usr/bin/env bash
# runpodBootstrap.sh (modular version - LOCAL EXECUTION)
#
# Local-side bootstrap that runs on YOUR MACHINE.
# Uses SSH to execute commands on the remote RunPod instance.
# Uses the step runner pattern to execute modular steps.
#
# Usage:
#   ./runpodBootstrap.sh [options]
#
# Options:
#   --comfyui        enable ComfyUI setup (default)
#   --no-comfyui     disable ComfyUI setup
#   --kohya          enable kohya setup (default off)
#   --dry-run        print actions only, don't execute
#   --force          force rerun of all steps (ignore state)
#   --from STEP      start from specific step (e.g., 30_conda)
#   --only STEP      run only specific step
#   --skip STEP      skip specific step
#   --list           list available steps and exit
#   -h, --help       show this help

set -euo pipefail

# Script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNPOD_DIR="$SCRIPT_DIR"
LIB_DIR="$RUNPOD_DIR/lib"
STEPS_DIR="$RUNPOD_DIR/steps"
LOGDIR="$RUNPOD_DIR/logs"

# Defaults (respect env from runpodFromSSH.sh)
ENABLE_COMFYUI="${ENABLE_COMFYUI:-1}"
ENABLE_KOHYA="${ENABLE_KOHYA:-0}"

DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="${DRY_PREFIX:-[]}"

FORCE="${FORCE:-0}"

export DRY_RUN DRY_PREFIX FORCE ENABLE_COMFYUI ENABLE_KOHYA

FROM_STEP=""
ONLY_STEP=""
SKIP_STEPS=()
LIST_STEPS=0

# Load common libraries
# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

usage() {
  sed -n '2,20p' "$0"
  exit 0
}

listSteps() {
  echo "Available steps:"
  echo
  echo "  10_diagnostics    - System diagnostics and template drift check"
  echo "  20_base_tools     - Install base system tools via apt"
  echo "  30_conda          - Setup miniconda and conda environment"
  echo "  40_comfyui        - Setup ComfyUI (optional, default on)"
  echo "  50_kohya          - Setup Kohya SS (optional, default off)"
  echo "  60_upload_models  - Show model upload instructions"
  echo
  echo "Use --from, --only, --skip to control step execution"
  exit 0
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --comfyui) ENABLE_COMFYUI=1; shift ;;
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;
    --kohya) ENABLE_KOHYA=1; shift ;;
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
    *)
      echo "ERROR: unknown option: $1"
      usage
      ;;
  esac
done

# Handle --list
if [[ "$LIST_STEPS" == "1" ]]; then
  listSteps
fi

# Setup logging
mkdir -p "$LOGDIR"
LOGFILE="$LOGDIR/bootstrap.$(date +"%Y%m%d_%H%M%S").log"

# Tee output to log file
if [[ "$DRY_RUN" != "1" ]]; then
  exec > >(tee -a "$LOGFILE") 2>&1
  log "logging to $LOGFILE"
fi

# Export workspace variables for steps
export WORKSPACE_ROOT RUNPOD_DIR CONDA_DIR COMFY_DIR KOHYA_DIR WORKFLOWS_DIR
export ENV_NAME STATE_FILE

log "runpod bootstrap (modular)"
echo "comfyui   : $ENABLE_COMFYUI"
echo "kohya     : $ENABLE_KOHYA"
echo "dry run   : $DRY_RUN"
echo "force     : $FORCE"
echo "state file: $STATE_FILE"
echo

# Define steps to run
ALL_STEPS=(
  "10_diagnostics"
  "20_base_tools"
  "30_conda"
)

# Add optional steps based on flags
if [[ "$ENABLE_COMFYUI" == "1" ]]; then
  ALL_STEPS+=("40_comfyui")
fi

if [[ "$ENABLE_KOHYA" == "1" ]]; then
  ALL_STEPS+=("50_kohya")
fi

ALL_STEPS+=("60_upload_models")

# Filter steps based on --from, --only, --skip
STEPS_TO_RUN=()

if [[ -n "$ONLY_STEP" ]]; then
  # Run only specified step
  STEPS_TO_RUN=("$ONLY_STEP")
else
  # Start from beginning or --from step
  START_FOUND=0
  if [[ -z "$FROM_STEP" ]]; then
    START_FOUND=1
  fi
  
  for step in "${ALL_STEPS[@]}"; do
    # Check if we should start
    if [[ "$START_FOUND" == "0" ]]; then
      if [[ "$step" == "$FROM_STEP" ]]; then
        START_FOUND=1
      else
        continue
      fi
    fi
    
    # Check if step should be skipped
    SKIP=0
    for skip_step in "${SKIP_STEPS[@]}"; do
      if [[ "$step" == "$skip_step" ]]; then
        SKIP=1
        break
      fi
    done
    
    if [[ "$SKIP" == "0" ]]; then
      STEPS_TO_RUN+=("$step")
    fi
  done
fi

# Run steps
log "running steps: ${STEPS_TO_RUN[*]}"

for step in "${STEPS_TO_RUN[@]}"; do
  STEP_SCRIPT="$STEPS_DIR/${step}.sh"
  
  if [[ ! -f "$STEP_SCRIPT" ]]; then
    warn "step script not found: $STEP_SCRIPT"
    continue
  fi
  
  logTask $step
  
  # Make executable
  chmod +x "$STEP_SCRIPT"
  
  # Run step
  if ! bash "$STEP_SCRIPT"; then
    die "step failed: $step"
  fi
done

# Create bash aliases
log "creating ~/.bash_aliases"
if [[ "$DRY_RUN" == "1" ]]; then
  dryrun  "echo 'alias d=\"ls -al\"' > ~/.bash_aliases"
else
  echo 'alias d="ls -al"' > ~/.bash_aliases
fi


log "bootstrap complete"
log "log file: $LOGFILE"
