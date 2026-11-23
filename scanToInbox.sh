#!/usr/bin/env bash
# scanToInbox.sh: duplex-scan with NAPS2 straight into the myCabinets Inbox.
#
#   scanToInbox.sh [--inbox DIR] [--device NAME] [--front] [--color] [--profile NAME]
#   scanToInbox.sh --list
#
# Load the hopper and run it. The ScanSnap S1300i is chosen by a partial
# device name. Duplex, A4, 300 dpi, grayscale, deskew and English OCR are
# the defaults. --front scans one side. A saved NAPS2 profile (--profile)
# is the way to drop blank duplex backs: the NAPS2 command line cannot.
# Guide: documentation/pdfFiler.md
set -euo pipefail

usage() {
    cat <<'EOF'
scanToInbox.sh: duplex-scan into the myCabinets Inbox with NAPS2.

  scanToInbox.sh [--inbox DIR] [--device NAME] [--front] [--color] [--profile NAME]
  scanToInbox.sh --list
  scanToInbox.sh --help

Defaults: device "ScanSnap", ADF duplex, A4, 300 dpi, grayscale, deskew,
English OCR. The PDF is YYYY-MM-DD-HHMMSS.pdf in the Inbox
(~/Documents/myCabinets/Inbox).

  --front            Scan one side (NAPS2 source "feeder")
  --color            Scan in colour
  --device NAME      Partial scanner name (default ScanSnap)
  --inbox DIR        Folder to write (default ~/Documents/myCabinets/Inbox)
  --profile NAME     Use a saved NAPS2 profile, still written to the Inbox
  --list             List SANE devices and exit
EOF
}

# Source logUtils.sh. LOG_UTILS overrides the lookup. Otherwise ask the
# active python3, then the py312 environment, so this runs with no conda
# environment active. There is no fallback logger.
_logUtilsFind() {
    local packageDir python
    if [[ -n "${LOG_UTILS:-}" ]]; then
        printf '%s' "$LOG_UTILS"
        return 0
    fi
    for python in python3 "${CONDA_DIR:-$HOME/miniconda3}/envs/py312/bin/python3"; do
        if packageDir="$("$python" -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))' 2>/dev/null)"; then
            printf '%s' "$packageDir/logUtils.sh"
            return 0
        fi
    done
    return 1
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

if ! _LOG_UTILS="$(_logUtilsFind)" || [[ ! -f "$_LOG_UTILS" ]]; then
    echo "ERROR: organiseMyProjects logUtils.sh not found; install organiseMyProjects or set LOG_UTILS" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$_LOG_UTILS"
setApplication "scanToInbox"

inbox="${SCAN_INBOX:-$HOME/Documents/myCabinets/Inbox}"
device="${SCAN_DEVICE:-ScanSnap}"
source="duplex"
bitdepth="gray"
profile=""
listOnly=0

_needValue() {
    local option="$1"
    local value="${2:-}"
    if [[ -z "$value" || "$value" == --* ]]; then
        log_error "$option needs a value"
        exit 2
    fi
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --inbox)
            _needValue "$1" "${2:-}"
            inbox="$2"
            shift 2
            ;;
        --device)
            _needValue "$1" "${2:-}"
            device="$2"
            shift 2
            ;;
        --profile)
            _needValue "$1" "${2:-}"
            profile="$2"
            shift 2
            ;;
        --front)
            source="feeder"
            shift
            ;;
        --color)
            bitdepth="color"
            shift
            ;;
        --list)
            listOnly=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            log_error "unknown option: $1"
            exit 2
            ;;
    esac
done

if ! command -v naps2 >/dev/null 2>&1; then
    log_error "naps2 not found. Install the NAPS2 deb; the Flatpak build does not see extra SANE drivers."
    exit 1
fi

runStart
if [[ "$listOnly" -eq 1 ]]; then
    log_doing "listing scanners"
    line
    naps2 console --listdevices --driver sane
    line
    log_done "listing scanners"
    exit 0
fi

if [[ ! -d "$inbox" ]]; then
    log_error "Inbox folder not found: $inbox"
    exit 1
fi
inbox="$(readlink -f "$inbox")"
output="$inbox/$(date +%Y-%m-%d-%H%M%S).pdf"

log_doing "scanning to the inbox"
log_value "inbox" "$inbox"
log_value "output" "$output"
if [[ -n "$profile" ]]; then
    log_value "profile" "$profile"
else
    log_value "device" "$device"
    log_value "source" "$source"
fi
line

# --ocrlang implies OCR. A profile supplies its own device and blank-page
# settings; --front and --color still override that profile.
args=(console -v --ocrlang eng -o "$output")
if [[ -n "$profile" ]]; then
    args+=(-p "$profile")
    if [[ "$source" == "feeder" ]]; then
        args+=(--source feeder)
    fi
    if [[ "$bitdepth" == "color" ]]; then
        args+=(--bitdepth color)
    fi
else
    args+=(
        --noprofile --driver sane --device "$device"
        --source "$source" --pagesize a4 --dpi 300 --bitdepth "$bitdepth" --deskew
    )
fi

log_action "scanning with naps2"
naps2 "${args[@]}"
if [[ ! -f "$output" ]]; then
    log_error "naps2 finished without writing $output"
    exit 1
fi
line
log_value "wrote" "$output"
log_done "scanning to the inbox"
