#!/bin/bash
#set -x

# Configuration

ROOT="/mnt/home/Andy/Documents/myCabinets"
INBOX="$ROOT/Inbox"

DOC_TYPES=(
"Invoice"
"Statement"
"Receipt"
"Policy Documents"
"P60"
"Payslip"
"LetterTo"
"LetterFrom"
"Renewal"
"Certificate of Insurance"
"Keep Original Name"
"Other"
)

# Functions

extract_date_from_pdf() {
    local file="$1"
    local text date d m y tmp dummy

    # Text layer first
    text=$(pdftotext -f 1 -l 1 "$file" - 2>/dev/null || true)

    # OCR fallback
    if [ -z "$text" ] && command -v ocrmypdf >/dev/null 2>&1; then
        tmp=$(mktemp)
        dummy=$(mktemp --suffix=.pdf)
        ocrmypdf --sidecar "$tmp" "$file" "$dummy" >/dev/null 2>&1 || true
        text=$(cat "$tmp" 2>/dev/null || true)
        rm -f "$tmp" "$dummy"
    fi

    # YYYY-MM-DD or YYYY/MM/DD
    date=$(echo "$text" | grep -Eo '[0-9]{4}[-/][0-9]{2}[-/][0-9]{2}' | head -1)
    if [ -n "$date" ]; then
        echo "${date//\//-}"
        return 0
    fi

    # DD/MM/YYYY or DD-MM-YYYY
    date=$(echo "$text" | grep -Eo '[0-9]{2}[/-][0-9]{2}[/-][0-9]{4}' | head -1)
    if [ -n "$date" ]; then
        d=${date:0:2}
        m=${date:3:2}
        y=${date:6:4}
        echo "$y-$m-$d"
        return 0
    fi

    return 1
}

closePreviewWindow() {
    local title="$1"
    wmctrl -c "$title" 2>/dev/null || true
}

# Main Loop (Batch Mode)
while true; do

    FILE=$(ls -t "$INBOX"/*.pdf 2>/dev/null | tail -1 || true)

    if [ -z "$FILE" ]; then
        zenity --info --text="Inbox is empty. All documents processed."
        exit 0
    fi

    BASENAME_ORIG=$(basename "$FILE")

    # Generate Preview
    TMPDIR=$(mktemp -d)
    pdftoppm -png -f 1 -l 1 "$FILE" "$TMPDIR/page" >/dev/null 2>&1

    TMPPNG="$TMPDIR/page-1.png"

    if [ ! -f "$TMPPNG" ]; then
        zenity --warning --text="Preview could not be generated for $BASENAME_ORIG"
    fi

    # Show persistent preview
    zenity --info \
      --title="Preview - $BASENAME_ORIG" \
      --width=600 --height=800 \
      --text="Preview of first page.\nThis stays open until filing completes.\n\nDocument: $BASENAME_ORIG" \
      --window-icon="$TMPPNG" \
      &
    PREVIEW_PID=$!

    # Give preview window time to appear
    sleep 0.3
    command -v wmctrl >/dev/null && wmctrl -r "Preview - $BASENAME_ORIG" -b add,above

    # Choose Folder
    FOLDER=$(zenity --file-selection \
            --directory \
            --title="Choose Filing Folder" \
            --filename="$ROOT/")

    if [ $? -ne 0 ]; then
        closePreviewWindow "Preview - $BASENAME_ORIG"
        rm -rf "$TMPDIR"
        exit 0
    fi

    case "$FOLDER" in
        "$ROOT"/*) ;;
        *)
            zenity --error --text="Folder must be inside $ROOT"
            closePreviewWindow "Preview - $BASENAME_ORIG"
            rm -rf "$TMPDIR"
            continue
        ;;
    esac

    FOLDERNAME=$(basename "$FOLDER")

    # Choose Document Type
    DOC_TYPE=$(zenity --list \
        --title="Document Type" \
        --text="Choose document type for $BASENAME_ORIG" \
        --column="Type" \
        --width=400 \
        --height=600 \
        "${DOC_TYPES[@]}")

    if [ $? -ne 0 ]; then
        closePreviewWindow "Preview - $BASENAME_ORIG"
        rm -rf "$TMPDIR"
        exit 0
    fi

    # sanitise and handle "Keep Original Name" specially
    ORIG_NAME_NO_EXT="${BASENAME_ORIG%.pdf}"

    if [[ "$DOC_TYPE" == "Keep Original Name" ]]; then
        # use original document name (without extension), sanitised
        NAME_PART=$(echo "$ORIG_NAME_NO_EXT" | sed 's/[\/:*?"<>|]/-/g')
    else
        # use chosen document type
        NAME_PART=$(echo "$DOC_TYPE" | sed 's/[\/:*?"<>|]/-/g')
    fi

    # build final filename
    FINAL="$DATE - $FOLDERNAME - $NAME_PART.pdf"
    DEST="$FOLDER/$FINAL"

    # Extract Date
    if DATE_EXTRACTED=$(extract_date_from_pdf "$FILE"); then
        DATE="$DATE_EXTRACTED"
    else
        DATE=$(date +%Y-%m-%d)
    fi

    # Build Final Name
    FINAL="$DATE - $FOLDERNAME - $NAME_PART.pdf"
    DEST="$FOLDER/$FINAL"

    zenity --question --text="File:\n$BASENAME_ORIG\n\nAs:\n$DEST\n\nProceed?"

    if [ $? -ne 0 ]; then
        closePreviewWindow "Preview - $BASENAME_ORIG"
        rm -rf "$TMPDIR"
        continue
    fi

    # Move File
    mv "$FILE" "$DEST"

    #zenity --info --text="Filed:\n$DEST"

    # Cleanup
    closePreviewWindow "Preview - $BASENAME_ORIG"
    rm -rf "$TMPDIR"

done
