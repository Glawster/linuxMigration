#!/usr/bin/env bash
set -euo pipefail

# Config
sourceRoot="$HOME/pst_import"
imports=("andyw@glawster.com.2025" "kathyMail" "myMail")

# Override profile manually if needed (leave empty for auto-detect)
profileDir="$HOME/.var/app/org.mozilla.Thunderbird/.thunderbird/r0q0pjdo.default-esr"

# Arg parsing
dryRun=0
if [[ "${1-}" == "--dry-run" ]]; then
  dryRun=1
  echo "Dry-run mode enabled — no changes will be written."
  echo
fi

# Helper: run command (respects dry-run)
run() {
  echo "+ $*"
  if [[ "${dryRun}" -eq 0 ]]; then
    eval "$@"
  fi
}

# Find Thunderbird profile
findThunderbirdProfile() {
  if [[ -n "${profileDir}" ]]; then
    return 0
  fi

  local candidates=(
    "$HOME/.var/app/org.mozilla.Thunderbird/.thunderbird"
  )

  for root in "${candidates[@]}"; do
    if [[ -d "${root}" ]]; then
      profileDir="$(ls -d "${root}"/*.default* 2>/dev/null | head -n1 || true)"
      if [[ -n "${profileDir}" ]]; then
        return 0
      fi
    fi
  done

  echo "Error: Could not detect Thunderbird profile directory."
  exit 1
}

# Backup the profile Mail directory
backupMailDir() {
  local mailDir="${profileDir}/Mail"

  if [[ "${dryRun}" -eq 1 ]]; then
    echo "[] back up: $(shortenPath "${mailDir}")"
    echo
    return
  fi

  if [[ -d "${mailDir}" ]]; then
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local backupDir="${mailDir}.backup-${timestamp}"
    echo "Backing up: $(shortenPath "${mailDir}")"
    echo "     to:    $(shortenPath "${backupDir}")"
    run "cp -a \"${mailDir}\" \"${backupDir}\""
    echo
  else
    echo "Warning: Mail directory not found at $(shortenPath "${mailDir}")"
    echo
  fi
}

# Combine message files into mbox format
createMboxFromDirectory() {
  local srcDir="$1"
  local destFile="$2"

  if [[ "${dryRun}" -eq 1 ]]; then
    echo "     [] create: $(shortenPath "${destFile}")"
    return
  fi
  
  # Build a proper mbox with "From " separators
  : > "${destFile}"  # truncate/create

  (
    cd "${srcDir}" || exit 1
    # Only include regular files, ignore subdirectories
    find . -maxdepth 1 -type f -printf '%f\n' | sort -n
  ) | while read -r msgFile; do
    # Simple mbox separator; Thunderbird uses message headers for real dates
    printf 'From - %s\n' "$(date)" >> "${destFile}"
    cat "${srcDir}/${msgFile}" >> "${destFile}"
    printf '\n' >> "${destFile}"
  done
}

# Import an individual tree (Inbox, Sent Items, etc.)
importTree() {
  local importName="$1"
  local srcBase="${sourceRoot}/${importName}"

  if [[ ! -d "${srcBase}" ]]; then
    echo "Skipping missing import: ${importName}"
    echo
    return
  fi

  echo "=== Importing ${importName} ==="

  local localFolders="${profileDir}/Mail/Local Folders"
  local rootMailbox="${localFolders}/${importName}"
  local rootSbd="${rootMailbox}.sbd"

  if [[ "${dryRun}" -eq 1 ]]; then
    echo "[] create mailbox and folder: ${rootMailbox}"
  else
    mkdir -p "${localFolders}"
    touch "${rootMailbox}"
    mkdir -p "${rootSbd}"
  fi

  # Walk subdirectories
  while IFS= read -r -d '' dir; do
    local relPath="${dir#${srcBase}}"
    relPath="${relPath#/}"

    # Skip Deleted Items folders
    if [[ "${relPath}" == "Deleted Items"* ]]; then
      echo "  -> Skipping Deleted Items folder: $(shortenPath "${relPath}")"
      continue
    fi

    [[ -z "${relPath}" ]] && continue

    # Count regular files and subdirectories in this folder
    local fileCount dirCount
    fileCount=$(find "${dir}" -maxdepth 1 -type f | wc -l)
    dirCount=$(find "${dir}" -mindepth 1 -maxdepth 1 -type d | wc -l)

    # Log what we're looking at
    echo "  -> $(shortenPath "${relPath}") (${fileCount} files, ${dirCount} subfolders)"

    # If it has subdirectories but no files, it's just a container → skip as leaf
    if [[ "${fileCount}" -eq 0 && "${dirCount}" -gt 0 ]]; then
      continue
    fi

    # If it has neither files nor subdirectories, it's empty → skip
    if [[ "${fileCount}" -eq 0 && "${dirCount}" -eq 0 ]]; then
      continue
    fi

    IFS='/' read -r -a parts <<< "${relPath}"
    local parent="${rootSbd}"

    # build parent chain under Local Folders/importName.sbd
    for (( i=0; i<${#parts[@]}-1; i++ )); do
      local folder="${parts[$i]}"
      if [[ "${dryRun}" -eq 1 ]]; then
        echo "     [] create parent: $(shortenPath "${parent}/${folder}")"
      else
        touch "${parent}/${folder}"
        mkdir -p "${parent}/${folder}.sbd"
      fi
      parent="${parent}/${folder}.sbd"
    done

    local leaf="${parts[-1]}"
    local destMbox="${parent}/${leaf}"

    echo "     => $(shortenPath "${destMbox}")"
    createMboxFromDirectory "${dir}" "${destMbox}"

  done < <(find "${srcBase}" -type d -print0)

  echo
}

# Truncate a path to the last characters so total length ≤ 110
shortenPath() {
  local fullPath="$1"
  local max=90

  local len=${#fullPath}
  if (( len <= max )); then
    echo "$fullPath"
  else
    # Keep last max-20 characters and prefix with …
    local tail="${fullPath: -(max-20)}"
    echo "...${tail}"
  fi
}

# Main
findThunderbirdProfile
echo "Using profile:       $(shortenPath "${profileDir}")"
echo "Local Folders path:  $(shortenPath "${profileDir}/Mail/Local Folders")"
echo

backupMailDir

for importName in "${imports[@]}"; do
  importTree "${importName}"
done

echo "Import complete. Restart Thunderbird to see:"
printf "  - %s\n" "${imports[@]}"
