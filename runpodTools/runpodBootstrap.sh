#!/usr/bin/env bash
# runpodBootstrap.sh (modular version - LOCAL EXECUTION)
#
# Local-side bootstrap that runs on YOUR MACHINE.
# Uses SSH to execute commands on the remote RunPod instance.
# Uses the step runner pattern to execute modular steps.
#
# Usage:
#   ./runpodBootstrap.sh [options] [ssh user@host -p PORT -i KEY]
#   ./runpodBootstrap.sh [options] user@host -p PORT -i KEY
#
# Options:
#   --comfyui        enable ComfyUI setup (default)
#   --no-comfyui     disable ComfyUI setup
#   --kohya          enable kohya setup (default off)
#   --llava          enable LLaVA setup (default off)
#   --dry-run        print actions only, don't execute
#   --force          force rerun of all steps (ignore state)
#   --from STEP      start from specific step (e.g., 30_conda)
#   --only STEP      run only specific step
#   --skip STEP      skip specific step
#   --list           list available steps and exit
#   -h, --help       show this help

set -euo pipefail

# RunPod defaults (used unless overridden)
POD_ROOT="${POD_ROOT:-/}"   # remote-ish default; local can override

# If user explicitly set WORKSPACE_ROOT, respect it.
# Otherwise choose a default depending on POD_ROOT:
if [[ -z "${WORKSPACE_ROOT:-}" ]]; then
  if [[ "$POD_ROOT" == "/" ]]; then
    # remote RunPod convention
    WORKSPACE_ROOT="/workspace"
  else
    # local test convention (your Path A)
    WORKSPACE_ROOT="$POD_ROOT/workspace"
  fi
fi
POD_HOME="${POD_HOME:-$POD_ROOT/root}"

# Script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNPOD_DIR="$SCRIPT_DIR"
LIB_DIR="$RUNPOD_DIR/lib"
STEPS_DIR="$RUNPOD_DIR/steps"
LOGDIR="$RUNPOD_DIR/logs"
TESTDIR="$RUNPOD_DIR/test"

# Defaults (respect env from runpodFromSSH.sh)
ENABLE_COMFYUI="${ENABLE_COMFYUI:-1}"
ENABLE_KOHYA="${ENABLE_KOHYA:-0}"
ENABLE_LLAVA="${ENABLE_LLAVA:-0}"

DRY_RUN="${DRY_RUN:-0}"
DRY_PREFIX="${DRY_PREFIX:-[]}"

FORCE="${FORCE:-0}"

export DRY_RUN DRY_PREFIX FORCE ENABLE_COMFYUI ENABLE_KOHYA ENABLE_LLAVA

FROM_STEP=""
ONLY_STEP=""
SKIP_STEPS=()
LIST_STEPS=0

# Load common libraries
# shellcheck disable=SC1091
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

usage() {
  sed -n '2,20p' "$0"
  exit 0
}

discoverSteps() {
  # Discover all step scripts in the steps directory
  # Returns sorted list of step basenames (without .sh extension)
  local steps=()
  if [[ -d "$STEPS_DIR" ]]; then
    while IFS= read -r -d '' step_file; do
      local step_name
      step_name=$(basename "$step_file" .sh)
      steps+=("$step_name")
    done < <(find "$STEPS_DIR" -maxdepth 1 -name "[0-9]*_*.sh" -type f -print0 | sort -z)
  fi
  printf '%s\n' "${steps[@]}"
}

extractStepDescription() {
  # Extract description from step script comment (line 3)
  local step_file="$1"
  if [[ -f "$step_file" ]]; then
    sed -n '3s/^# //p' "$step_file"
  fi
}

resolveStepName() {
  # Resolve short form step name to full step name
  # e.g., "20" or "20_base" matches "20_base_tools"
  # Uses DISCOVERED_STEPS_CACHE if available, otherwise discovers steps
  local short_name="$1"
  local available_steps
  
  # Use cache if available, otherwise discover
  if [[ ${#DISCOVERED_STEPS_CACHE[@]} -gt 0 ]]; then
    available_steps=("${DISCOVERED_STEPS_CACHE[@]}")
  else
    mapfile -t available_steps < <(discoverSteps)
  fi
  
  # First try exact match
  for step in "${available_steps[@]}"; do
    if [[ "$step" == "$short_name" ]]; then
      echo "$step"
      return 0
    fi
  done
  
  # Then try prefix match
  for step in "${available_steps[@]}"; do
    if [[ "$step" == "${short_name}"* ]]; then
      echo "$step"
      return 0
    fi
  done
  
  # No match found
  return 1
}

listSteps() {
  echo "Available steps:"
  echo
  
  local steps
  mapfile -t steps < <(discoverSteps)
  
  for step in "${steps[@]}"; do
    local step_file="$STEPS_DIR/${step}.sh"
    local description
    description=$(extractStepDescription "$step_file")
    printf "  %-18s - %s\n" "$step" "$description"
  done
  
  echo
  echo "Use --from, --only, --skip to control step execution"
  echo "Short forms supported: --only 20 (matches 20_base_tools)"
  exit 0
}

# Parse arguments
CONN_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --comfyui) ENABLE_COMFYUI=1; shift ;;
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;
    --kohya) ENABLE_KOHYA=1; shift ;;
    --llava) ENABLE_LLAVA=1; shift ;;
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
    ssh)
      shift
      CONN_ARGS=("$@")
      set -- # clear remaining args (we've captured them)
      break
      ;;
    *@*)
      # allow: ./runpodBootstrap.sh --only 40 root@1.2.3.4 -p 123 -i key
      CONN_ARGS=("$@")
      set --
      break
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage
      ;;
  esac
done

# Handle --list
if [[ "$LIST_STEPS" == "1" ]]; then
  listSteps
fi

# ------------------------------------------------------------
# Connection handling
# ------------------------------------------------------------
# Supports:
#   ./runpodBootstrap.sh ... ssh user@host -p PORT -i KEY
#   ./runpodBootstrap.sh ... user@host -p PORT -i KEY
#   SSH_TARGET=... ./runpodBootstrap.sh ...
#
# If CONN_ARGS were provided, they override env vars.
if [[ ${#CONN_ARGS[@]} -gt 0 ]]; then
  SSH_TARGET_ARG=""
  SSH_PORT_ARG=""
  SSH_IDENTITY_ARG=""

  # allow optional leading "ssh"
  if [[ "${CONN_ARGS[0]}" == "ssh" ]]; then
    CONN_ARGS=("${CONN_ARGS[@]:1}")
  fi

  while [[ ${#CONN_ARGS[@]} -gt 0 ]]; do
    case "${CONN_ARGS[0]}" in
      -p)
        SSH_PORT_ARG="${CONN_ARGS[1]:-}"
        CONN_ARGS=("${CONN_ARGS[@]:2}")
        ;;
      -i)
        SSH_IDENTITY_ARG="${CONN_ARGS[1]:-}"
        CONN_ARGS=("${CONN_ARGS[@]:2}")
        ;;
      *)
        if [[ -z "$SSH_TARGET_ARG" ]]; then
          SSH_TARGET_ARG="${CONN_ARGS[0]}"
          CONN_ARGS=("${CONN_ARGS[@]:1}")
        else
          die "unexpected connection arg: ${CONN_ARGS[0]}"
        fi
        ;;
    esac
  done

  if [[ -z "$SSH_TARGET_ARG" ]]; then
    die "missing ssh user@host"
  fi

  export SSH_TARGET="$SSH_TARGET_ARG"
  export SSH_PORT="$SSH_PORT_ARG"
  export SSH_IDENTITY="$SSH_IDENTITY_ARG"
fi

# If we're doing any remote work, we require SSH_TARGET to be set (either env or args)
if [[ -z "${SSH_TARGET:-}" ]]; then
  die "missing target. use: ... ssh user@host -p PORT -i KEY  (or set SSH_TARGET=...)"
fi

export REQUIRE_REMOTE=1
export DRY_RUN

# Now SSH variables are final, build ssh options
# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts

# Cache discovered steps for efficiency
DISCOVERED_STEPS_CACHE=()
mapfile -t DISCOVERED_STEPS_CACHE < <(discoverSteps)

# Resolve short form step names to full names
if [[ -n "$FROM_STEP" ]]; then
  ORIGINAL_FROM="$FROM_STEP"
  if ! FROM_STEP=$(resolveStepName "$FROM_STEP"); then
    die "unknown step: $ORIGINAL_FROM"
  fi
fi

if [[ -n "$ONLY_STEP" ]]; then
  ORIGINAL_ONLY="$ONLY_STEP"
  if ! ONLY_STEP=$(resolveStepName "$ONLY_STEP"); then
    die "unknown step: $ORIGINAL_ONLY"
  fi
fi

if [[ ${#SKIP_STEPS[@]} -gt 0 ]]; then
  RESOLVED_SKIP_STEPS=()
  for skip_step in "${SKIP_STEPS[@]}"; do
    if resolved=$(resolveStepName "$skip_step"); then
      RESOLVED_SKIP_STEPS+=("$resolved")
    else
      die "unknown step: $skip_step"
    fi
  done
  SKIP_STEPS=("${RESOLVED_SKIP_STEPS[@]}")
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
echo "llava     : $ENABLE_LLAVA"
echo "dry run   : $DRY_RUN"
echo "force     : $FORCE"
echo "state file: $STATE_FILE"
echo

# Dynamically discover all available steps
mapfile -t ALL_AVAILABLE_STEPS < <(discoverSteps)

# Define steps to run based on discovered steps and feature flags
ALL_STEPS=()

for step in "${ALL_AVAILABLE_STEPS[@]}"; do
  # Apply conditional logic for optional steps
  case "$step" in
    40_comfyui)
      if [[ "$ENABLE_COMFYUI" == "1" ]]; then
        ALL_STEPS+=("$step")
      fi
      ;;
    50_kohya)
      if [[ "$ENABLE_KOHYA" == "1" ]]; then
        ALL_STEPS+=("$step")
      fi
      ;;
    70_llava)
      if [[ "$ENABLE_LLAVA" == "1" ]]; then
        ALL_STEPS+=("$step")
        # Also ensure llava adapter step is included
        if ! [[ " ${ALL_STEPS[*]} " == *" 75_llava_adapter "* ]]; then
          ALL_STEPS+=("75_llava_adapter")
        fi
      fi
      ;;
    75_llava_adapter)
      if [[ "$ENABLE_LLAVA" == "1" ]]; then
        ALL_STEPS+=("$step")
        # Ensure llava step is also included
        if ! [[ " ${ALL_STEPS[*]} " == *" 70_llava "* ]]; then
          ALL_STEPS+=("70_llava") 
        fi
      fi
      ;;
    *)
      # Include all other steps by default
      ALL_STEPS+=("$step")
      ;;
  esac
done

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
  
  logTask "$step"
  
  # Make executable
  chmod +x "$STEP_SCRIPT"
  
  # Run step
  if ! bash "$STEP_SCRIPT"; then
    die "step failed: $step"
  fi
done

log "bootstrap complete"
log "log file: $LOGFILE"