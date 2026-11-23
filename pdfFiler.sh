#!/usr/bin/env bash
# pdfFiler.sh: file the PDFs in the myCabinets Inbox, one at a time.
#
# For each PDF in the inbox (oldest first) it shows page 1, asks for the
# cabinet folder and document type, works out the document date and files it
# as:
#
#   <folder>/<yyyy-mm-dd> - <folder name> - <type>.pdf
#
# Safe by default: without -y/--confirm the dialogs run but nothing moves.
# Nothing is overwritten or deleted. A PDF already in the chosen folder (same
# content, any name) goes to the desktop Trash; a different file with the same
# name leaves the PDF in the inbox.
#
# The script can be sourced (tests do) without running anything.
# Guide: documentation/pdfFiler.md
set -euo pipefail

_PDF_FILER_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
_APPLICATION="pdfFiler"

_DOC_TYPES=(
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

_MONTHS='(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*'

## cli

cliFail() {
    printf '%s: %s\n' "$_APPLICATION" "$1" >&2
    exit 2
}

# Parse arguments into the globals dryRun, rootDir and inboxDir.
cliParse() {
    dryRun=1
    rootDir="$HOME/Documents/myCabinets"
    inboxDir=""

    while (($#)); do
        case "$1" in
            -h | --help)
                cliUsage
                exit 0
                ;;
            --version)
                printf '%s %s\n' "$_APPLICATION" "$(cliVersion)"
                exit 0
                ;;
            -y | --confirm)
                dryRun=""
                shift
                ;;
            --root | --inbox)
                (($# >= 2)) || cliFail "$1 needs a folder"
                if [[ "$1" == --root ]]; then rootDir="$2"; else inboxDir="$2"; fi
                shift 2
                ;;
            *)
                cliFail "unknown argument '$1' (see $_APPLICATION --help)"
                ;;
        esac
    done
    inboxDir="${inboxDir:-$rootDir/Inbox}"
}

cliUsage() {
    cat <<'USAGE'
Usage: pdfFiler.sh [-y|--confirm] [--root DIR] [--inbox DIR]

File the PDFs in the myCabinets Inbox one at a time: preview page 1, choose
the cabinet folder and document type, and file it as

  <folder>/<yyyy-mm-dd> - <folder name> - <type>.pdf

The date is read from the PDF (OCR when it has no text), then the file name,
and is asked for when neither has one.

Previews by default: the dialogs run but nothing moves without --confirm.

  -y, --confirm   move the files (default is a preview)
  --root DIR      cabinets folder (default ~/Documents/myCabinets)
  --inbox DIR     folder to file from (default <root>/Inbox)
  --version       show the version
  -h, --help      show this help

A PDF already in the chosen folder (same content) is sent to the Trash. A
different file with the same name is never overwritten; the PDF stays in the
inbox.
USAGE
}

# The repository version, or "unknown" outside a checkout.
cliVersion() {
    if declare -F repoVersionDescribe >/dev/null; then
        repoVersionDescribe
    else
        printf 'unknown'
    fi
}

## date

# Print the document date (yyyy-mm-dd) from a file name, or fail.
dateFromFilename() {
    local name="${1%.*}" found

    found="$(grep -Eo '20[0-9]{2}[-_.][0-9]{2}[-_.][0-9]{2}' <<<"$name" | head -1 || true)"
    if [[ -n "$found" ]] && dateValidate "$(tr '._' '--' <<<"$found")"; then
        return 0
    fi

    found="$(grep -Eo '20[0-9]{6}' <<<"$name" | head -1 || true)"
    if [[ -n "$found" ]] && dateValidate "${found:0:4}-${found:4:2}-${found:6:2}"; then
        return 0
    fi

    found="$(grep -Eo '[0-9]{2}[-_.][0-9]{2}[-_.]20[0-9]{2}' <<<"$name" | head -1 || true)"
    if [[ -n "$found" ]] && dateValidate "${found:6:4}-${found:3:2}-${found:0:2}"; then
        return 0
    fi
    return 1
}

# Print the document date (yyyy-mm-dd) from page-1 text, or fail. Candidates
# are tried most specific first, and each must be a real calendar date:
#   1. a line that is only a date, such as "30 October 2026" (bank statements)
#   2. a date after a label: "Date:", "Statement date", "Invoice date", ...
#   3. the first written-month date anywhere ("30 Oct 2026")
#   4. the first ISO date (2026-10-30 or 2026/10/30)
#   5. the first UK numeric date (30/10/2026 or 30-10-2026)
dateFromText() {
    local text="$1" candidate
    local written="[0-9]{1,2}(st|nd|rd|th)? $_MONTHS,? [0-9]{4}"
    local numeric="[0-9]{1,2}[/.-][0-9]{1,2}[/.-][0-9]{4}"

    while IFS= read -r candidate; do
        dateValidate "$(dateWrittenToIso "$candidate")" && return 0
    done < <(grep -Eo "^[[:space:]]*${written}[[:space:]]*\$" <<<"$text" || true)

    while IFS= read -r candidate; do
        candidate="$(grep -Eo "$written|$numeric|[0-9]{4}[-/][0-9]{2}[-/][0-9]{2}" <<<"$candidate" | head -1)"
        dateNormalise "$candidate" && return 0
    done < <(grep -Eio "(^|[^a-z])date[a-z ]*[: ]+($written|$numeric|[0-9]{4}[-/][0-9]{2}[-/][0-9]{2})" <<<"$text" || true)

    while IFS= read -r candidate; do
        dateValidate "$(dateWrittenToIso "$candidate")" && return 0
    done < <(grep -Eo "$written" <<<"$text" || true)

    while IFS= read -r candidate; do
        dateValidate "${candidate//\//-}" && return 0
    done < <(grep -Eo '[0-9]{4}[-/][0-9]{2}[-/][0-9]{2}' <<<"$text" || true)

    while IFS= read -r candidate; do
        dateNormalise "$candidate" && return 0
    done < <(grep -Eo "$numeric" <<<"$text" || true)
    return 1
}

# Print yyyy-mm-dd for any supported date form, or fail.
dateNormalise() {
    local value="$1" day month year
    if [[ "$value" =~ ^([0-9]{4})[-/]([0-9]{2})[-/]([0-9]{2})$ ]]; then
        dateValidate "${BASH_REMATCH[1]}-${BASH_REMATCH[2]}-${BASH_REMATCH[3]}"
    elif [[ "$value" =~ ^([0-9]{1,2})[/.-]([0-9]{1,2})[/.-]([0-9]{4})$ ]]; then
        # UK order: day first.
        day="$(printf '%02d' "$((10#${BASH_REMATCH[1]}))")"
        month="$(printf '%02d' "$((10#${BASH_REMATCH[2]}))")"
        year="${BASH_REMATCH[3]}"
        dateValidate "$year-$month-$day"
    else
        dateValidate "$(dateWrittenToIso "$value")"
    fi
}

# Print the yyyy-mm-dd it was given if it is a real calendar date, or fail.
# date -d rolls 2026-02-31 over to March, so the round trip must match.
dateValidate() {
    local iso="$1"
    [[ "$iso" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || return 1
    [[ "$(date -d "$iso" +%F 2>/dev/null)" == "$iso" ]] || return 1
    printf '%s' "$iso"
}

# Turn "30th Oct, 2026" into something date -d reads, then into yyyy-mm-dd.
dateWrittenToIso() {
    local value="$1"
    value="$(sed -E 's/([0-9])(st|nd|rd|th)/\1/; s/,//; s/\bSept\b/Sep/' <<<"$value")"
    date -d "$value" +%F 2>/dev/null || true
}

# Print the date of a PDF: page-1 text, OCR when there is no text layer, then
# the file name. Fails when none has a date.
dateOfPdf() {
    local file="$1" text sidecar scratchPdf
    text="$(pdftotext -f 1 -l 1 "$file" - 2>/dev/null || true)"

    if [[ -z "${text//[[:space:]]/}" ]] && command -v ocrmypdf >/dev/null; then
        sidecar="$(mktemp)"
        scratchPdf="$(mktemp --suffix=.pdf)"
        ocrmypdf --sidecar "$sidecar" "$file" "$scratchPdf" >/dev/null 2>&1 || true
        text="$(cat "$sidecar" 2>/dev/null || true)"
        rm -f -- "$sidecar" "$scratchPdf"
    fi

    dateFromText "$text" || dateFromFilename "$(basename "$file")"
}

## environment

# Source the shared organiseMyProjects logUtils.sh. LOG_UTILS overrides the
# lookup (tests use it). Otherwise ask the active python3, then the py312
# environment this repository's .envrc uses, so the script also runs from a
# shell where no conda environment is active. There is no fallback logger.
environmentLogUtilsLoad() {
    local candidate packageDir python
    candidate="${LOG_UTILS:-}"
    if [[ -z "$candidate" ]]; then
        for python in python3 "${CONDA_DIR:-$HOME/miniconda3}/envs/py312/bin/python3"; do
            if packageDir="$("$python" -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))' 2>/dev/null)"; then
                candidate="$packageDir/logUtils.sh"
                break
            fi
        done
    fi
    if [[ -z "$candidate" || ! -f "$candidate" ]]; then
        echo "ERROR: organiseMyProjects logUtils.sh not found; install organiseMyProjects or set LOG_UTILS" >&2
        exit 1
    fi
    # shellcheck source=/dev/null
    source "$candidate"
}

# Validate and normalise rootDir and inboxDir.
environmentPathsValidate() {
    [[ -d "$rootDir" ]] || { log_error "Cabinets folder not found: $rootDir"; exit 1; }
    [[ -d "$inboxDir" ]] || { log_error "Inbox folder not found: $inboxDir"; exit 1; }
    rootDir="$(readlink -f "$rootDir")"
    inboxDir="$(readlink -f "$inboxDir")"
}

# Fail fast when a required external tool is missing. ocrmypdf, feh, eog and
# wmctrl are optional.
environmentToolsCheck() {
    local tool missing=()
    for tool in pdftotext pdftoppm zenity gio cmp date; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done
    if ((${#missing[@]})); then
        log_error "Missing required tools: ${missing[*]} (poppler-utils, zenity, libglib2.0-bin)"
        exit 1
    fi
}

## file

# Print the first file in folder identical to pdf; fail if none.
fileDuplicateFind() {
    local pdf="$1" folder="$2" existing
    for existing in "$folder"/*; do
        [[ -f "$existing" ]] || continue
        if cmp -s -- "$pdf" "$existing"; then
            printf '%s' "$existing"
            return 0
        fi
    done
    return 1
}

# Print the name part used in the filed name: the folder the PDF is filed in,
# or its parent when that folder is a year (Bank Statements/2026 files as
# "Bank Statements", not "2026").
fileFolderLabel() {
    local folder="$1" label
    label="$(basename "$folder")"
    if [[ "$label" =~ ^(19|20)[0-9]{2}$ ]]; then
        label="$(basename "$(dirname "$folder")")"
    fi
    printf '%s' "$label"
}

# Print the inbox PDFs, oldest first, one per line. Matches .pdf and .PDF.
fileInboxList() {
    local dir="$1"
    find "$dir" -maxdepth 1 -type f -iname '*.pdf' -printf '%T@\t%p\n' | sort -n | cut -f2-
}

# Replace characters not allowed in file names.
fileNameClean() {
    sed 's/[\/:*?"<>|]/-/g' <<<"$1"
}

# File one PDF through the dialogs. Returns 0 to carry on with the next PDF
# and 1 when the user cancelled the run. Updates main's counters.
fileOne() {
    local pdf="$1" name folder docType namePart docDate destination existing
    name="$(basename "$pdf")"
    log_value "file" "$name"

    if ! previewShow "$pdf"; then
        guiMessage warning "Preview could not be generated for $name"
    fi

    if ! folder="$(guiChooseFolder)"; then
        previewClose
        return 1
    fi
    folder="$(readlink -f "$folder")"
    if [[ "$folder" != "$rootDir"/* ]]; then
        guiMessage error "Folder must be inside $rootDir"
        log_warn "folder outside cabinets, left in inbox: $name"
        previewClose
        ((skipped += 1))
        return 0
    fi

    if ! docType="$(guiChooseType "$name")"; then
        previewClose
        return 1
    fi
    if [[ "$docType" == "Keep Original Name" ]]; then
        namePart="$(fileNameClean "${name%.*}")"
    else
        namePart="$(fileNameClean "$docType")"
    fi

    if ! docDate="$(dateOfPdf "$pdf")"; then
        if ! docDate="$(guiAskDate)"; then
            previewClose
            return 1
        fi
    fi

    destination="$folder/$docDate - $(fileFolderLabel "$folder") - $namePart.pdf"

    # Already filed here under any name: nothing to keep.
    if existing="$(fileDuplicateFind "$pdf" "$folder")"; then
        log_action "trash $name: already filed as $(basename "$existing")"
        [[ -n "${dryRun:-}" ]] || gio trash -- "$pdf"
        ((duplicates += 1))
        previewClose
        return 0
    fi

    # Never overwrite a different document.
    if [[ -e "$destination" ]]; then
        guiMessage error "A different file already exists:\n$destination\n\n$name stays in the inbox."
        log_warn "$(basename "$destination") already exists with different content; left in inbox: $name"
        ((conflicts += 1))
        previewClose
        return 0
    fi

    if ! guiConfirm "File:\n$name\n\nAs:\n$destination\n\nProceed?"; then
        log_info "declined, left in inbox: $name"
        ((skipped += 1))
        previewClose
        return 0
    fi

    log_action "move $name → ${destination#"$rootDir"/}"
    if [[ -z "${dryRun:-}" ]]; then
        mv -n -- "$pdf" "$destination"
        if [[ -e "$pdf" || ! -f "$destination" ]]; then
            log_error "Move failed, original kept: $pdf"
            exit 1
        fi
    fi
    ((filed += 1))
    previewClose
}

## gui

# Ask for the document date; prints yyyy-mm-dd, fails on cancel. Asks again
# until the date is real.
guiAskDate() {
    local entered prompt="No date found in the PDF or its name.\n\nEnter date (YYYY-MM-DD):"
    while true; do
        entered="$(zenity --entry --title="Document Date" --text="$prompt" --entry-text="")" || return 1
        [[ -n "$entered" ]] || return 1
        dateValidate "$entered" && return 0
        prompt="'$entered' is not a valid date.\n\nEnter date (YYYY-MM-DD):"
    done
}

guiChooseFolder() {
    zenity --file-selection --directory --title="Choose Filing Folder" --filename="$rootDir/"
}

guiChooseType() {
    zenity --list --title="Document Type" --text="Choose document type for $1" \
        --column="Type" --width=400 --height=600 "${_DOC_TYPES[@]}"
}

# Ask to proceed. In a preview the question says nothing will move.
guiConfirm() {
    local text="$1"
    [[ -z "${dryRun:-}" ]] || text="$text\n\n(Preview: nothing will move. Run with --confirm to file.)"
    zenity --question --text="$text"
}

# Show a zenity message: guiMessage info|warning|error TEXT.
guiMessage() {
    zenity "--$1" --text="$2" || true
}

## preview

# Close the page-1 preview window and remove its image.
previewClose() {
    if [[ -n "${previewPid:-}" ]] && kill -0 "$previewPid" 2>/dev/null; then
        kill "$previewPid" 2>/dev/null || true
    fi
    if [[ -n "${previewTitle:-}" ]] && command -v wmctrl >/dev/null; then
        wmctrl -c "$previewTitle" 2>/dev/null || true
    fi
    previewPid=""
    previewTitle=""
    rm -f -- "$previewDir"/page-*.png
}

# Show page 1 of a PDF in an image window beside the dialogs. Fails when the
# page cannot be rendered.
previewShow() {
    local pdf="$1" image
    pdftoppm -png -f 1 -l 1 "$pdf" "$previewDir/page" >/dev/null 2>&1 || return 1
    image="$(find "$previewDir" -maxdepth 1 -name 'page-*.png' | head -1)"
    [[ -n "$image" ]] || return 1

    previewTitle="pdfFiler Preview - $(basename "$pdf")"
    if command -v feh >/dev/null; then
        feh --title "$previewTitle" --zoom-fill --geometry 700x900+20+20 "$image" &
        previewPid=$!
    elif command -v eog >/dev/null; then
        eog --new-instance "$image" &
        previewPid=$!
    else
        return 0
    fi

    # Place the window top-left so the dialogs do not hide it.
    sleep 0.3
    if command -v wmctrl >/dev/null; then
        wmctrl -r "$previewTitle" -e 0,20,20,700,900 2>/dev/null || true
    fi
}

## main

main() {
    local pdf pdfs=() filed=0 duplicates=0 conflicts=0 skipped=0 cancelled="" mode

    if [[ -f "$_PDF_FILER_DIR/repoVersion.sh" ]]; then
        # shellcheck source=repoVersion.sh
        source "$_PDF_FILER_DIR/repoVersion.sh"
    fi
    cliParse "$@"
    environmentLogUtilsLoad
    setApplication "$_APPLICATION"
    environmentToolsCheck
    environmentPathsValidate

    # One private scratch folder for preview images, removed however the run
    # ends. (Never reuse the name TMPDIR: mktemp and other tools read it.)
    previewDir="$(mktemp -d)"
    trap 'previewClose; rm -rf -- "$previewDir"' EXIT

    mode="confirm"
    [[ -z "${dryRun:-}" ]] || mode="preview (use --confirm to move files)"

    runStart
    log_doing "filing inbox pdfs"
    log_value "version" "$(cliVersion)"
    log_value "cabinets" "$rootDir"
    log_value "inbox" "$inboxDir"
    log_value "mode" "$mode"
    line

    # Take the list once, so a PDF the user declines is not offered again.
    mapfile -t pdfs < <(fileInboxList "$inboxDir")
    if ((${#pdfs[@]} == 0)); then
        log_info "inbox is empty"
    fi
    for pdf in "${pdfs[@]}"; do
        if ! fileOne "$pdf"; then
            cancelled=1
            log_info "cancelled by user"
            break
        fi
    done

    line
    log_value "filed" "$filed"
    log_value "already filed, trashed" "$duplicates"
    log_value "name taken, left in inbox" "$conflicts"
    log_value "skipped" "$skipped"
    log_done "filing inbox pdfs"

    if [[ -z "$cancelled" ]] && ((${#pdfs[@]} > 0)); then
        guiMessage info "Inbox done: $filed filed, $duplicates already filed, $((conflicts + skipped)) left in the inbox."
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
