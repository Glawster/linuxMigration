#!/usr/bin/env bash
# Find and reorganise Direct Payments spreadsheet statement files.

set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source the shared organiseMyProjects logUtils.sh. LOG_UTILS overrides the
# lookup. Otherwise ask the active python3, then the py312 environment this
# repository's .envrc uses, so the script also runs from a shell where no conda
# environment is active. There is no fallback logger: fail with a clear error.
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

if ! _LOG_UTILS="$(_logUtilsFind)" || [[ ! -f "$_LOG_UTILS" ]]; then
    echo "ERROR: organiseMyProjects logUtils.sh not found; install organiseMyProjects or set LOG_UTILS" >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$_LOG_UTILS"

setApplication "fixDirectPaymentsStatements"

DOCS_DIR="$HOME/Documents"
dryRun=1

if [[ "${1:-}" == "--confirm" ]]; then
    dryRun=0
else
    echo "=== DRY RUN: no files will actually be moved. Pass --confirm to execute. ==="
fi

if [ ! -e "$DOCS_DIR" ]; then
    log_error "$DOCS_DIR not found."
    exit 1
fi

DOCS_DIR="$(readlink -f "$DOCS_DIR")"
BASE_TARGET="$DOCS_DIR/myCabinets/Benefits/Statements"

log_value "documents resolved to" "$DOCS_DIR"
log_value "base target for statements" "$BASE_TARGET"
echo

doMove() {
    local src="$1"
    local destDir="$2"

    if [ "$dryRun" -eq 1 ]; then
        log_action "$src would be moved to $destDir"
        return 0
    fi

    mkdir -p "$destDir"
    if mv -i "$src" "$destDir/"; then
        log_info "$src moved to $destDir"
    fi
}

log_doing "scanning for statement files"
echo

# Use find to follow symlinks and capture Excel statement files
find -L "$DOCS_DIR" -type f \( -iname "*.xlsx" -o -iname "*.xls" \) | while read -r file; do

    # Skip files inside the correct target hierarchy already
    if [[ "$file" == "$BASE_TARGET/"* ]]; then
        log_info "skip (already under myCabinets tree): $file"
        continue
    fi

    filename="$(basename "$file")"

    #
    # --------------------------
    # Pattern A:
    #   YYYY-MM-DD - Name.xlsx
    # --------------------------
    #
    if [[ "$filename" =~ ^([0-9]{4})-([0-9]{2})-([0-9]{2})\ -\ (.+)\.(xlsx|xls)$ ]]; then
        year="${BASH_REMATCH[1]}"
        person="${BASH_REMATCH[4]}"

        destDir="$BASE_TARGET/$year/$person"
        doMove "$file" "$destDir"
        continue
    fi

    #
    # --------------------------
    # Pattern B:
    #   Name.YYYYMMDD.xlsx
    # --------------------------
    #
    if [[ "$filename" =~ ^(.+)\.([0-9]{8})\.(xlsx|xls)$ ]]; then
        person="${BASH_REMATCH[1]}"
        date="${BASH_REMATCH[2]}"
        year="${date:0:4}"

        destDir="$BASE_TARGET/$year/$person"
        doMove "$file" "$destDir"
        continue
    fi

    log_info "no match (leaving in place): $file"

done

echo
log_done "done fixing direct payment statements"
if [ "$dryRun" -eq 1 ]; then
    log_info "this was a dry run; no files were actually moved."
fi

