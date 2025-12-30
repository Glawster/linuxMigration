#!/usr/bin/env bash
set -euo pipefail

PROFILE="${SWTOR_PROFILE:-baseline}"

LOG_DIR="${HOME}/swtor-logs"
mkdir -p "$LOG_DIR"
TS="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="${LOG_DIR}/swtor_${PROFILE}_${TS}.log"

echo "swtor launch..." | tee -a "$LOG_FILE"
echo "...profile: ${PROFILE}" | tee -a "$LOG_FILE"
echo "...log: ${LOG_FILE}" | tee -a "$LOG_FILE"
echo "...command: $*" | tee -a "$LOG_FILE"

# Proton log (normally writes ~/steam-<appid>.log)
export PROTON_LOG=1
# Optional: keep Proton logs in one place
# export PROTON_LOG_DIR="$LOG_DIR"  # note: some containerized setups have quirks here :contentReference[oaicite:2]{index=2}

case "$PROFILE" in
  baseline) ;;
  launcher) ;;
  wined3d)  export PROTON_USE_WINED3D=1 ;;
  audio)    export WINEDLLOVERRIDES="xaudio2_7=n,b" ;;
  safe)     export PROTON_NO_ESYNC=1; export PROTON_NO_FSYNC=1 ;;
  *) echo "ERROR: Unknown SWTOR_PROFILE: $PROFILE" | tee -a "$LOG_FILE"; exit 2 ;;
esac

# IMPORTANT: run the game command Steam gives us
exec "$@" 2>&1 | tee -a "$LOG_FILE"
