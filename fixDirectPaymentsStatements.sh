#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="$HOME/Documents"
DRYRUN=0

if [[ "${1:-}" == "--dryrun" || "${1:-}" == "--dry-run" ]]; then
    DRYRUN=1
    echo "=== DRY RUN: no files will actually be moved ==="
fi

if [ ! -e "$DOCS_DIR" ]; then
    echo "ERROR: $DOCS_DIR not found."
    exit 1
fi

DOCS_DIR="$(readlink -f "$DOCS_DIR")"
BASE_TARGET="$DOCS_DIR/myCabinets/directPayments/Statements"

echo "Documents resolved to: $DOCS_DIR"
echo "Base target for statements: $BASE_TARGET"
echo

doMove() {
    local src="$1"
    local destDir="$2"

    if [ "$DRYRUN" -eq 1 ]; then
        echo "$src would be moved to $destDir"
        return 0
    fi

    mkdir -p "$destDir"
    if mv -i "$src" "$destDir/"; then
        echo "$src moved to $destDir"
    fi
}

echo "=== scanning for statement files ==="
echo

# Use find to follow symlinks and capture Excel statement files
find -L "$DOCS_DIR" -type f \( -iname "*.xlsx" -o -iname "*.xls" \) | while read -r file; do

    # Skip files inside the correct target hierarchy already
    if [[ "$file" == "$BASE_TARGET/"* ]]; then
        echo "skip (already under myCabinets tree): $file"
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

    echo "no match (leaving in place): $file"

done

echo
echo "=== done fixing direct payment statements ==="
if [ "$DRYRUN" -eq 1 ]; then
    echo "NOTE: this was a dry run; no files were actually moved."
fi

