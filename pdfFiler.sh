#!/usr/bin/env bash
set -euo pipefail

# Configuration
sourceRoot="$HOME/pst_mbox"
imports=("andyw@glawster.com.2025" "kathyMail" "myMail")

# Override profile manually if needed (leave empty for auto-detect)
profileDir="~/.var/app/org.mozilla.Thunderbird/.thunderbird/r0q0pjdo.default-esr"

# Flags
dryRun=0
if [[ "${1-}" == "--dry-run" ]]; then
  dryRun=1
  echo "Dry-run mode enabled — no changes will be written."
  echo
fi

# Run command (respects dry-run)
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
    "$HOME/.thunderbird"
    "$HOME/snap/thunderbird/common/.thunderbird"
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
    echo "[DRY-RUN] Would back up: ${mailDir}"
    echo
    return
  fi

  if [[ -d "${mailDir}" ]]; then
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local backupDir="${mailDir}.backup-${timestamp}"
    echo "Backing up: ${mailDir}"
    echo "     to:    ${backupDir}"
    run "cp -a \"${mailDir}\" \"${backupDir}\""
    echo
  else
    echo "Warning: Mail directory not found at ${mailDir}"
    echo
  fi
}

# Combine message files into mbox format
createMboxFromDirectory() {
  local srcDir="$1"
  local destFile="$2"

  if [[ "${dryRun}" -eq 1 ]]; then
    echo "[DRY-RUN] Would create mbox: ${destFile}"
    return
  fi

  (
    cd "${srcDir}" || exit 1
    ls | sort -n | xargs cat -- 
  ) > "${destFile}"
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
    echo "[DRY-RUN] Would create mailbox and folder: ${rootMailbox}"
  else
    touch "${rootMailbox}"
    mkdir -p "${rootSbd}"
  fi

  # Walk subdirectories
  while IFS= read -r -d '' dir; do
    local relPath="${dir#${srcBase}}"
    relPath="${relPath#/}"

    [[ -z "${relPath}" ]] && continue

    if ! find "${dir}" -maxdepth 1 -type f -print -quit | grep -q .; then
      continue
    fi

    IFS='/' read -r -a parts <<< "${relPath}"
    local parent="${rootSbd}"

    for (( i=0; i<${#parts[@]}-1; i++ )); do
      local folder="${parts[$i]}"
      if [[ "${dryRun}" -eq 1 ]]; then
        echo "[DRY-RUN] Would create parent mailbox: ${parent}/${folder}"
      else
        touch "${parent}/${folder}"
        mkdir -p "${parent}/${folder}.sbd"
      fi
      parent="${parent}/${folder}.sbd"
    done

    local leaf="${parts[-1]}"
    local destMbox="${parent}/${leaf}"

    echo "  -> ${relPath} => ${destMbox}"
    createMboxFromDirectory "${dir}" "${destMbox}"

  done < <(find "${srcBase}" -type d -print0)

  echo
}

# Main Execution
findThunderbirdProfile
echo "Using profile:       ${profileDir}"
echo "Local Folders path:  ${profileDir}/Mail/Local Folders"
echo

backupMailDir

for importName in "${imports[@]}"; do
  importTree "${importName}"
done

echo "Import complete. Restart Thunderbird to see:"
printf "  - %s\n" "${imports[@]}"
