#!/usr/bin/env bash
set -euo pipefail

# -------------------------
# config
# -------------------------
DOCS_DIR="$HOME/Documents"
ONEDRIVE_DIR="$HOME/Cloud/OneDrive"   # CHANGE IF NEEDED

dryRun=1
if [[ "${1:-}" == "--confirm" ]]; then
    dryRun=0
else
    echo "=== DRY RUN: no files will actually be moved. Pass --confirm to execute. ==="
fi

echo "=== organising Office-style files under: $DOCS_DIR ==="

if [ ! -e "$DOCS_DIR" ]; then
    echo "ERROR: $DOCS_DIR not found."
    exit 1
fi

# Resolve symlink (important for WindowsArchive etc.)
DOCS_DIR="$(readlink -f "$DOCS_DIR")"
echo "resolved Documents path: $DOCS_DIR"
echo "excluding folder: $DOCS_DIR/myCabinets"

# -------------------------
# helper: doMove with dryrun support
# -------------------------
doMove() {
    local src="$1"
    local destDir="$2"

    if [ "$dryRun" -eq 1 ]; then
        echo "$src would be moved to $destDir"
        return 0
    fi

    if mv -i "$src" "$destDir/"; then
        echo "$src moved to $destDir"
    fi
}

# -------------------------
# helper: find files (follows symlinks, skips myCabinets)
# -------------------------
findFiles() {
    local pattern="$1"

    find -L "$DOCS_DIR" \
        -path "$DOCS_DIR/myCabinets" -prune -o \
        -type f -iname "$pattern" -print
}

# -------------------------
# helper: generic organiser
# -------------------------
moveFiles() {
    local pattern="$1"
    local subdir="$2"

    local dest="$DOCS_DIR/$subdir"

    echo ">>> organising files matching '$pattern' into: $dest"
    mkdir -p "$dest"

    findFiles "$pattern" | while read -r file; do
        # skip if already in destination
        if [[ "$file" == "$dest/"* ]]; then
            #echo "skip (already organised): $file"
            continue
        fi

        doMove "$file" "$dest"
    done
}

# -------------------------
# Excel-like files
# -------------------------
moveFiles "*.xlsx" "officeFiles/excelFiles"
moveFiles "*.xlsm" "officeFiles/excelFiles"
moveFiles "*.xls"  "officeFiles/excelFiles"
moveFiles "*.ods"  "officeFiles/excelFiles"
moveFiles "*.csv"  "officeFiles/excelFiles"

# -------------------------
# Word-like files
# -------------------------
moveFiles "*.docx" "officeFiles/wordFiles"
moveFiles "*.doc"  "officeFiles/wordFiles"
moveFiles "*.rtf"  "officeFiles/wordFiles"
moveFiles "*.odt"  "officeFiles/wordFiles"

# -------------------------
# PowerPoint-like files
# -------------------------
moveFiles "*.pptx" "officeFiles/powerpointFiles"
moveFiles "*.ppt"  "officeFiles/powerpointFiles"
moveFiles "*.odp"  "officeFiles/powerpointFiles"

# -------------------------
# Publisher
# -------------------------
moveFiles "*.pub"  "officeFiles/publisherFiles"

# -------------------------
# MS Project
# -------------------------
moveFiles "*.mpp"  "officeFiles/projectFiles"
moveFiles "*.mpt"  "officeFiles/projectFiles"

# -------------------------
# Visio
# -------------------------
moveFiles "*.vsd"   "officeFiles/visioFiles"
moveFiles "*.vsdx"  "officeFiles/visioFiles"
moveFiles "*.vsdm"  "officeFiles/visioFiles"
moveFiles "*.vdx"   "officeFiles/visioFiles"

# -------------------------
# Other Office-ish formats (.opd, etc.)
# -------------------------
moveFiles "*.opd"   "officeFiles/otherOfficeFiles"

# -------------------------
# OneNote (*.one) -> OneDrive
# -------------------------
echo ">>> organising OneNote *.one files"

if [ -d "$ONEDRIVE_DIR" ]; then
    ONEDRIVE_DIR="$(readlink -f "$ONEDRIVE_DIR")"
    mkdir -p "$ONEDRIVE_DIR"

    findFiles "*.one" | while read -r file; do
        if [[ "$file" == "$ONEDRIVE_DIR/"* ]]; then
            #echo "skip (already in OneDrive): $file"
            continue
        fi
        doMove "$file" "$ONEDRIVE_DIR"
    done
else
    echo "SKIP: OneDrive not found at $ONEDRIVE_DIR"
fi

# -------------------------
# MindManager (*.mmap) -> myMaps
# -------------------------
echo ">>> organising MindManager *.mmap files"

MYMAPS="$DOCS_DIR/myMaps"
mkdir -p "$MYMAPS"

findFiles "*.mmap" | while read -r file; do
    if [[ "$file" == "$MYMAPS/"* ]]; then
        #echo "skip (already in myMaps): $file"
        continue
    fi

    doMove "$file" "$MYMAPS"
done

echo "=== done organising Office-style files ==="
if [ "$dryRun" -eq 1 ]; then
    echo "NOTE: this was a dry run; no files were actually moved."
fi

