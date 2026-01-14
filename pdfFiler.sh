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

close_preview() {
    # Try to close by PID (feh/eog)
    if [ -n "${PREVIEW_PID:-}" ] && kill -0 "$PREVIEW_PID" 2>/dev/null; then
        kill "$PREVIEW_PID" 2>/dev/null || true
    fi

    # Also attempt to close by window title (belt + braces)
    if [ -n "${PREVIEW_TITLE:-}" ] && command -v wmctrl >/dev/null 2>&1; then
        wmctrl -c "$PREVIEW_TITLE" 2>/dev/null || true
    fi
}

extract_date_from_filename() {
    local name="$1"
    local y m d date

    # Strip extension
    name="${name%.*}"

    # Match YYYY-MM-DD or YYYY_MM_DD or YYYY.MM.DD
    date=$(echo "$name" | grep -Eo '20[0-9]{2}[-_.][0-9]{2}[-_.][0-9]{2}' | head -1 || true)
    if [ -n "$date" ]; then
        echo "$date" | tr '._' '-'
        return 0
    fi

    # Match YYYYMMDD
    date=$(echo "$name" | grep -Eo '20[0-9]{2}[0-9]{2}[0-9]{2}' | head -1 || true)
    if [ -n "$date" ]; then
        y="${date:0:4}"; m="${date:4:2}"; d="${date:6:2}"
        echo "$y-$m-$d"
        return 0
    fi

    # Match DD-MM-YYYY / DD_MM_YYYY / DD.MM.YYYY
    date=$(echo "$name" | grep -Eo '[0-9]{2}[-_.][0-9]{2}[-_.]20[0-9]{2}' | head -1 || true)
    if [ -n "$date" ]; then
        d="${date:0:2}"
        m="${date:3:2}"
        y="${date:6:4}"
        echo "$y-$m-$d"
        return 0
    fi

    return 1
}

# Main Loop (Batch Mode)
while true; do

    FILE=$(ls -t "$INBOX"/*.pdf 2>/dev/null | tail -1 || true)

    if [ -z "$FILE" ]; then
        zenity --info --text="Inbox is empty. All documents processed."
        close_preview
        rm -rf "$TMPDIR"
        exit 0
    fi

    BASENAME_ORIG=$(basename "$FILE")

    # Generate Preview (first page -> PNG)

    TMPDIR=$(mktemp -d)

    # Create page-1.png reliably
    pdftoppm -png -f 1 -l 1 "$FILE" "$TMPDIR/page" >/dev/null 2>&1
    TMPPNG="$TMPDIR/page-1.png"

    if [ ! -f "$TMPPNG" ]; then
        zenity --warning --text="Preview could not be generated for $BASENAME_ORIG"
        rm -rf "$TMPDIR"
        close_preview
        rm -rf "$TMPDIR"
        continue
    fi

    # Title we will use to identify/move/close the preview window
    PREVIEW_TITLE="pdfFiler Preview - $BASENAME_ORIG"

    # Launch a real image window (NOT zenity) so content shows
    # Use feh if available, fall back to eog.
    if command -v feh >/dev/null 2>&1; then
        feh --title "$PREVIEW_TITLE" --zoom-fill --geometry 700x900+20+20 "$TMPPNG" &
        PREVIEW_PID=$!
    elif command -v eog >/dev/null 2>&1; then
        eog --new-instance "$TMPPNG" &
        PREVIEW_PID=$!
    else
        # Worst-case fallback: at least show a message
        zenity --info --title="$PREVIEW_TITLE" --text="(Install 'feh' or 'eog' for preview images.)" &
        PREVIEW_PID=$!
    fi

    # Give the window time to appear, then place it
    sleep 0.3

    # Move it somewhere sensible (top-left) so it isn't hidden under dialogs
    # and keep it on the current workspace.
    if command -v wmctrl >/dev/null 2>&1; then
        # Attempt to move/resize (x,y,w,h). Adjust numbers if you want.
        wmctrl -r "$PREVIEW_TITLE" -e 0,20,20,700,900 2>/dev/null || true
    fi


    # Choose Folder
    FOLDER=$(zenity --file-selection \
            --directory \
            --title="Choose Filing Folder" \
            --filename="$ROOT/")

    if [ $? -ne 0 ]; then
        close_preview
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
        close_preview
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

    # --- Date selection: OCR -> filename -> prompt user (NOT current date) ---

    DATE=""

    # 1) OCR
    if DATE_EXTRACTED=$(extract_date_from_pdf "$WORKPDF"); then
        DATE="$DATE_EXTRACTED"
    fi

    # 2) Filename
    if [ -z "$DATE" ]; then
        if DATE_FROM_NAME=$(extract_date_from_filename "$BASENAME_ORIG"); then
            DATE="$DATE_FROM_NAME"
        fi
    fi

    # 3) Prompt user if still unknown
    if [ -z "$DATE" ]; then
        DATE=$(zenity --entry \
            --title="Document Date" \
            --text="No date found in OCR or filename.\n\nEnter date (YYYY-MM-DD):" \
            --entry-text="")

        # Cancel = stop script cleanly for this file
        if [ $? -ne 0 ] || [ -z "$DATE" ]; then
            close_preview 2>/dev/null || true
            rm -rf "$TMPDIR"
            exit 0
        fi
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
    close_preview
    rm -rf "$TMPDIR"

done
