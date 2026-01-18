#!/usr/bin/env bash
# runpodFromSsh.sh
#
# Takes the RunPod ssh command and calls runpodBootstrap.sh with defaults:
#   comfyui on, run on, kohya off
#
# Usage:
#   ./runpodFromSsh.sh [options] ssh user@host -p PORT -i KEY
#
# Options:
#   --kohya        enable kohya too
#   --no-comfyui   disable comfyui
#   --no-run       only write scripts, don't execute
#   --dry-run      call bootstrap with --dry-run (prints what would run + checks connectivity)
#   -h, --help     help
#
# Example:
#   ./runpodFromSsh.sh --dry-run ssh root@213.192.2.88 -p 40023 -i ~/.ssh/id_ed25519

set -euo pipefail

ENABLE_KOHYA=0
ENABLE_COMFYUI=1
RUN_REMOTE=1
DRY_RUN=0

usage() { sed -n '2,40p' "$0"; exit 0; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --kohya) ENABLE_KOHYA=1; shift ;;
    --no-comfyui) ENABLE_COMFYUI=0; shift ;;
    --no-run) RUN_REMOTE=0; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage ;;
    ssh) break ;;
    *) echo "ERROR: unknown option: $1"; usage ;;
  esac
done

if [[ $# -lt 2 || "$1" != "ssh" ]]; then
  echo "ERROR: expected ssh command after options"
  usage
fi
shift

TARGET=""
PORT="22"
IDENTITY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p) PORT="$2"; shift 2 ;;
    -i) IDENTITY="$2"; shift 2 ;;
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

BOOTSTRAP="./runpodBootstrap.sh"
if [[ ! -x "$BOOTSTRAP" ]]; then
  echo "ERROR: $BOOTSTRAP not found or not executable"
  exit 1
fi

ARGS=()
[[ "$DRY_RUN" == "1" ]] && ARGS+=(--dry-run)
[[ "$ENABLE_KOHYA" == "1" ]] && ARGS+=(--kohya)
[[ "$ENABLE_COMFYUI" == "0" ]] && ARGS+=(--no-comfyui)
[[ "$RUN_REMOTE" == "0" ]] && ARGS+=(--no-run)

ARGS+=("$TARGET" -p "$PORT")
[[ -n "$IDENTITY" ]] && ARGS+=(-i "$IDENTITY")

echo "calling bootstrap:"
echo "  $BOOTSTRAP ${ARGS[*]}"
echo

"$BOOTSTRAP" "${ARGS[@]}"
