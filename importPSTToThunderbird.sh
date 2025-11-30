#!/usr/bin/env bash
set -euo pipefail

# CONFIGURE THESE

# Where your three imports live
SOURCE_ROOT="$HOME/pst_import"

# The three top-level import trees you mentioned
IMPORTS=(
  "andyw@glawster.com.2025"
  "kathyMail"
  "myMail"
)

# FIND THUNDERBIRD PROFILE

PROFILE_ROOT=""
for d in "$HOME/.thunderbird" \
         "$HOME/snap/thunderbird/common/.thunderbird" \
         "$HOME/.var/app/org.mozilla.Thunderbird/.thunderbird"
do
  if [ -d "$d" ]; then
    PROFILE_ROOT="$d"
    break
  fi
done

if [ -z "$PROFILE_ROOT" ]; then
  echo "Could not find Thunderbird profile root. Edit script to set PROFILE_ROOT manually."
  exit 1
fi

PROFILE_DIR="$(ls -d "$PROFILE_ROOT"/*.default* 2>/dev/null | head -n1 || true)"
if [ -z "$PROFILE_DIR" ]; then
  echo "Could not find a *.default* profile under $PROFILE_ROOT"
  exit 1
fi

LOCAL_FOLDERS="$PROFILE_DIR/Mail/Local Folders"
mkdir -p "$LOCAL_FOLDERS"

echo "Using Local Folders at: $LOCAL_FOLDERS"
echo

# IMPORT FUNCTION

import_tree () {
  local import_name="$1"
  local src_base="$SOURCE_ROOT/$import_name"

  if [ ! -d "$src_base" ]; then
    echo "Skipping $import_name (not found at $src_base)"
    return
  fi

  echo "=== Importing $import_name ==="

  # Base mailbox and .sbd dir for subfolders
  touch "$LOCAL_FOLDERS/$import_name"
  mkdir -p "$LOCAL_FOLDERS/$import_name.sbd"

  # Walk all subdirs under this import tree
  while IFS= read -r -d '' dir; do
    # relative path from src_base
    local rel="${dir#$src_base}"
    rel="${rel#/}"   # strip leading slash

    # skip the root itself
    [ -z "$rel" ] && continue

    # does this directory contain any files (emails)?
    if ! find "$dir" -maxdepth 1 -type f -print -quit | grep -q .; then
      continue
    fi

    # split rel path into components
    IFS='/' read -r -a parts <<< "$rel"

    # build parent chain under Local Folders/import_name.sbd
    local parent="$LOCAL_FOLDERS/$import_name.sbd"
    local i
    for (( i=0; i<${#parts[@]}-1; i++ )); do
      local folder="${parts[$i]}"
      # parent mailbox file and its .sbd dir
      touch "$parent/$folder"
      parent="$parent/$folder.sbd"
      mkdir -p "$parent"
    done

    local leaf="${parts[-1]}"
    local dest_mbox="$parent/$leaf"

    echo "  -> $(printf '%s\n' "$rel")  =>  $(printf '%s\n' "$dest_mbox")"

    # combine all message files (one email per file) into a single mbox
    (
      cd "$dir"
      # sort numerically so messages stay in order
      ls | sort -n | xargs cat -- 
    ) > "$dest_mbox"

  done < <(find "$src_base" -type d -print0)

  echo
}

# RUN IMPORT

echo "Source root: $SOURCE_ROOT"
echo "Imports: ${IMPORTS[*]}"
echo

for name in "${IMPORTS[@]}"; do
  import_tree "$name"
done

echo "Done. Restart Thunderbird and look under 'Local Folders' for:"
printf '  - %s\n' "${IMPORTS[@]}"
