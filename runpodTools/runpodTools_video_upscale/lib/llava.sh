#!/usr/bin/env bash
# ------------------------------------------------------------
# lib/llava.sh
#
# Shared LLaVA configuration & helpers.
# ------------------------------------------------------------

# ------------------------------------------------------------
# Mode switch
# ------------------------------------------------------------

WORKSPACE_ROOT="${WORKSPACE:-/workspace}"

# Normalize truthy values
case "${JOYFUL,,}" in
  1|true|yes|on) LLAVA_JOYFUL=1 ;;
  *)             LLAVA_JOYFUL=0 ;;
esac

# ------------------------------------------------------------
# Model definitions
# ------------------------------------------------------------

# --- Original / default LLaVA ---
LLAVA_BASE_MODEL_NAME="${LLAVA_BASE_MODEL_NAME:-llava-v1.5-7b}"
LLAVA_BASE_MODEL_PATH="${LLAVA_BASE_MODEL_PATH:-liuhaotian/llava-v1.5-7b}"
LLAVA_BASE_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA}"
LLAVA_BASE_ENV_NAME="${LLAVA_ENV_NAME:-llava}"
LLAVA_BASE_VERSION="${LLAVA_BASE_VERSION:-1.5}"
LLAVA_BASE_REF="${LLAVA_BASE_REF:-v1.5}"

# --- JoyCaption / Joyful model ---
LLAVA_JOY_MODEL_NAME="${LLAVA_JOY_MODEL_NAME:-joycaption-alpha-two}"
LLAVA_JOY_MODEL_PATH="${LLAVA_JOY_MODEL_PATH:-fancyfeast/llama-joycaption-alpha-two-hf-llava}"
LLAVA_JOY_DIR="${LLAVA_DIR:-${WORKSPACE_ROOT}/LLaVA-JoyCaption}"
LLAVA_JOY_ENV_NAME="${LLAVA_ENV_NAME:-joycaption}"
LLAVA_JOY_VERSION="${LLAVA_JOY_VERSION:-alpha-two}"
LLAVA_JOY_REF="${LLAVA_JOY_REF:-main}"

# ------------------------------------------------------------
# Select active model
# ------------------------------------------------------------

if [[ "$LLAVA_JOYFUL" -eq 1 ]]; then
  LLAVA_MODEL_NAME="$LLAVA_JOY_MODEL_NAME"
  LLAVA_MODEL_PATH="$LLAVA_JOY_MODEL_PATH"
  LLAVA_DIR="$LLAVA_JOY_DIR"
  LLAVA_ENV_NAME="$LLAVA_JOY_ENV_NAME"
  LLAVA_VERSION="$LLAVA_JOY_VERSION"
  LLAVA_REF="$LLAVA_JOY_REF"
else
  LLAVA_MODEL_NAME="$LLAVA_BASE_MODEL_NAME"
  LLAVA_MODEL_PATH="$LLAVA_BASE_MODEL_PATH"
  LLAVA_DIR="$LLAVA_BASE_DIR"
  LLAVA_ENV_NAME="$LLAVA_BASE_ENV_NAME"
  LLAVA_VERSION="$LLAVA_BASE_VERSION"
  LLAVA_REF="$LLAVA_BASE_REF"
fi

# ------------------------------------------------------------
# Networking
# ------------------------------------------------------------

LLAVA_HOST="${LLAVA_HOST:-0.0.0.0}"

LLAVA_CONTROLLER_PORT="${LLAVA_CONTROLLER_PORT:-7001}"
LLAVA_WORKER_PORT="${LLAVA_WORKER_PORT:-7002}"
LLAVA_ADAPTER_PORT="${LLAVA_ADAPTER_PORT:-9188}"

LLAVA_CONTROLLER_URL="${LLAVA_CONTROLLER_URL:-http://${LLAVA_HOST}:${LLAVA_CONTROLLER_PORT}}"
LLAVA_WORKER_URL="${LLAVA_WORKER_URL:-http://${LLAVA_HOST}:${LLAVA_WORKER_PORT}}"
LLAVA_ADAPTER_URL="${LLAVA_ADAPTER_URL:-http://${LLAVA_HOST}:${LLAVA_ADAPTER_PORT}}"

# ------------------------------------------------------------
# API surface
# ------------------------------------------------------------

LLAVA_API_ROUTE="${LLAVA_API_ROUTE:-/analyze}"

# ------------------------------------------------------------
# Runtime
# ------------------------------------------------------------

LLAVA_CONDA_ENV="${LLAVA_CONDA_ENV:-llava}"
LLAVA_TIMEOUT_SECONDS="${LLAVA_TIMEOUT_SECONDS:-120}"

# ------------------------------------------------------------
# Validation helpers
# ------------------------------------------------------------

llava_validate_config() {
  local missing=0
  for v in \
    LLAVA_MODEL_NAME \
    LLAVA_MODEL_PATH \
    LLAVA_CONTROLLER_PORT \
    LLAVA_WORKER_PORT \
    LLAVA_ADAPTER_PORT
  do
    if [[ -z "${!v}" ]]; then
      echo "ERROR: $v is not set" >&2
      missing=1
    fi
  done
  return $missing
}

llava_dump_config() {
  echo "LLAVA_JOYFUL=$LLAVA_JOYFUL"
  echo "LLAVA_MODEL_NAME=$LLAVA_MODEL_NAME"
  echo "LLAVA_MODEL_PATH=$LLAVA_MODEL_PATH"
  set | grep '^LLAVA_' | sort
}
