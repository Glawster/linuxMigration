#!/usr/bin/env bash
set -euo pipefail
#
# importPSTToThunderbird.sh
#
# Purpose:
#   Import a pst-utils/readpst export into Thunderbird "Local Folders".
#
# Important:
#   readpst in recursive mode creates directories for folders and writes a file
#   named "mbox" inside each folder directory. Thunderbird does NOT read
#   <Folder>/mbox. Thunderbird expects an mbox file named exactly <Folder>
#   (no extension) plus an optional <Folder>.sbd directory for subfolders.
#
#   This script converts the readpst recursive layout into Thunderbird's mbox
#   layout.
#
# Typical workflow:
#   1) Convert PST:
#        mkdir -p ~/pst_imports
#        readpst -r -o ~/pst_imports /path/to/mail.pst
#
#   2) Import into Thunderbird Local Folders:
#        bash importPSTToThunderbird.sh
#

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

# Root directory containing one or more readpst output directories
sourceRoot="$HOME/pst_imports"

# Flatpak Thunderbird profile root (contains one or more *.default* profiles)
profileRoot="$HOME/.var/app/org.mozilla.Thunderbird/.thunderbird"

# ------------------------------------------------------------------
# Argument parsing
# ------------------------------------------------------------------

dryRun=0
if [[ "${1-}" == "--dry-run" ]]; then
  dryRun=1
  echo "Dry-run mode enabled — no files will be copied."
  echo
fi

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

shortenPath() {
  sed "s|$HOME|~|g" <<<"$1"
}

findThunderbirdProfile() {
  # Select the most recently modified Thunderbird profile directory.
  local best=""
  local bestMtime=0

  shopt -s nullglob
  for d in "$profileRoot"/*.default*; do
    [[ -d "$d" ]] || continue
    [[ -f "$d/prefs.js" ]] || continue

    local mtime
    mtime=$(stat -c %Y "$d/prefs.js" 2>/dev/null || echo 0)
    if (( mtime > bestMtime )); then
      bestMtime=$mtime
      best="$d"
    fi
  done
  shopt -u nullglob

  if [[ -z "$best" ]]; then
    echo "ERROR: Thunderbird profile not found under: $profileRoot" >&2
    exit 1
  fi

  profileDir="$best"
}

backupLocalFolders() {
  local localFolders="$1"
  local backupDir
  backupDir="${localFolders}.backup.$(date +%Y%m%d_%H%M%S)"

  echo "...backing up local folders to: $(shortenPath "$backupDir")"
  if [[ $dryRun -eq 0 ]]; then
    cp -a "$localFolders" "$backupDir"
  fi
}

# Convert a readpst recursive folder directory into Thunderbird format.
# srcDir is a directory that may contain a file named "mbox" and subfolder dirs.
# destDir is the directory where Thunderbird expects the mbox files for siblings.
importReadpstFolder() {
  local srcDir="$1"
  local destDir="$2"
  local folderName
  folderName=$(basename "$srcDir")

  # Skip non-mail artifacts that readpst may produce.
  # Calendar and Contacts are not mail folders for Thunderbird Local Folders.
  if [[ "$folderName" == "Calendar" || "$folderName" == "Contacts" ]]; then
    echo "...skipping non-mail folder: $folderName"
    return 0
  fi

  local srcMbox="$srcDir/mbox"
  local destMbox="$destDir/$folderName"
  local destSbd="$destDir/${folderName}.sbd"

  # If this folder contains mail, copy the mbox file to the expected location.
  if [[ -f "$srcMbox" ]]; then
    echo "...writing mbox: $(shortenPath "$destMbox")"
    if [[ $dryRun -eq 0 ]]; then
      # If a directory exists where the mbox file should be, remove it.
      if [[ -d "$destMbox" ]]; then
        rm -rf "$destMbox"
      fi
      cp -a "$srcMbox" "$destMbox"
    fi
  else
    # No mail at this level, but it may still have subfolders. Ensure a container file exists.
    if [[ $dryRun -eq 0 ]]; then
      if [[ ! -f "$destMbox" ]]; then
        : > "$destMbox"
      fi
    fi
  fi

  # Recurse into subfolders (directories other than readpst metadata)
  local hasSubfolders=0
  while IFS= read -r -d '' child; do
    hasSubfolders=1
    if [[ $dryRun -eq 0 ]]; then
      mkdir -p "$destSbd"
    fi
    importReadpstFolder "$child" "$destSbd"
  done < <(find "$srcDir" -mindepth 1 -maxdepth 1 -type d -print0)

  # If there are subfolders, Thunderbird expects a .sbd directory.
  # If there are none, we leave it as just an mbox file.
  if [[ $hasSubfolders -eq 1 ]]; then
    echo "...subfolders in: $folderName"
  fi
}

importTree() {
  local tree="$1"
  local src="$sourceRoot/$tree"

  echo "Importing tree: $tree"
  echo "  from: $(shortenPath "$src")"
  echo "  to:   $(shortenPath "$localFolders")"

  local dstRootMbox="$localFolders/$tree"
  local dstRootSbd="$localFolders/${tree}.sbd"

  if [[ $dryRun -eq 0 ]]; then
    # Ensure root container exists and is a FILE
    if [[ -d "$dstRootMbox" ]]; then
      rm -rf "$dstRootMbox"
    fi
    if [[ ! -f "$dstRootMbox" ]]; then
      : > "$dstRootMbox"
    fi

    # Recreate the .sbd container for this import
    rm -rf "$dstRootSbd"
    mkdir -p "$dstRootSbd"

    # Remove root index so Thunderbird rebuilds
    rm -f "$localFolders/${tree}.msf"
  fi

  # Import each top-level folder from the readpst export
  while IFS= read -r -d '' top; do
    importReadpstFolder "$top" "$dstRootSbd"
  done < <(find "$src" -mindepth 1 -maxdepth 1 -type d -print0)

  if [[ $dryRun -eq 0 ]]; then
    # Remove any copied indexes (Thunderbird will rebuild)
    find "$dstRootSbd" -type f -name "*.msf" -delete
  fi

  echo
}

# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if [[ ! -d "$sourceRoot" ]]; then
  echo "ERROR: source directory not found: $sourceRoot" >&2
  exit 1
fi

findThunderbirdProfile
localFolders="$profileDir/Mail/Local Folders"

if [[ ! -d "$localFolders" ]]; then
  echo "ERROR: Thunderbird Local Folders not found: $localFolders" >&2
  exit 1
fi

echo "Using profile:      $(shortenPath "$profileDir")"
echo "Local Folders path: $(shortenPath "$localFolders")"
echo "Source root:        $(shortenPath "$sourceRoot")"
echo

mapfile -t imports < <(find "$sourceRoot" -mindepth 1 -maxdepth 1 -type d -printf "%f
" | sort)

if [[ ${#imports[@]} -eq 0 ]]; then
  echo "No PST import directories found in $(shortenPath "$sourceRoot")"
  exit 0
fi

backupLocalFolders "$localFolders"
echo

for tree in "${imports[@]}"; do
  importTree "$tree"
done

echo "Import complete."
echo "Restart Thunderbird to view the imported folders under Local Folders."
