#!/usr/bin/env bash
set -euo pipefail

_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source logUtils.sh from organiseMyProjects (adjust path if needed)
_LOG_UTILS="$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))' 2>/dev/null)/logUtils.sh"
if [[ -f "$_LOG_UTILS" ]]; then
  source "$_LOG_UTILS"
else
  # Fallback: basic log function if organiseMyProjects not installed
  logFile="/dev/null"
  log_init()  { logFile="${HOME}/.local/state/${1}/${1}-$(date +%Y-%m-%d).log"; mkdir -p "$(dirname "$logFile")"; }
  log_info()  { echo "...$1"; }
  log_doing() { echo "$1..."; }
  log_done()  { echo "...$1"; }
  log_warn()  { echo "WARNING: $1" >&2; }
  log_error() { echo "ERROR: $1" >&2; }
  log_value() { echo "...$1: $2"; }
  log_action(){ echo "...$1"; }
  log_box()   { echo "=== $1 ==="; }
fi

log_init "organiseHome"

HOME_DIR="$HOME"

log_doing "organising $HOME_DIR"

# ----------------------------------------
# helper: make directory if it doesn't exist
# ----------------------------------------
make_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        log_action "creating directory: $dir"
        mkdir -p "$dir"
    else
        log_info "directory already exists: $dir"
    fi
}

# ----------------------------------------
# helper: move a path into a target dir if it exists
# ----------------------------------------
move_into_if_exists() {
    local src="$1"
    local target_dir="$2"

    if [ -e "$src" ]; then
        make_dir "$target_dir"
        log_action "moving $src -> $target_dir"
        mv -i "$src" "$target_dir/"
    else
        log_info "not found (skip): $src"
    fi
}

# ----------------------------------------
# 1. create top-level grouping directories
# ----------------------------------------
make_dir "$HOME_DIR/Apps"
make_dir "$HOME_DIR/Cloud"
make_dir "$HOME_DIR/Development"
make_dir "$HOME_DIR/Games"
make_dir "$HOME_DIR/Configs"
make_dir "$HOME_DIR/Archive"

echo

# ----------------------------------------
# 2. development-related items
# ----------------------------------------
log_doing "organising development-related items"
move_into_if_exists "$HOME_DIR/.vscode"     "$HOME_DIR/Development"
move_into_if_exists "$HOME_DIR/.conda"      "$HOME_DIR/Development"
move_into_if_exists "$HOME_DIR/miniconda3"  "$HOME_DIR/Development"

echo

# ----------------------------------------
# 3. gaming-related items
# ----------------------------------------
log_doing "organising gaming-related items"
# note: there is already a ~/Games directory; we just gather game stuff into it
move_into_if_exists "$HOME_DIR/.steam"      "$HOME_DIR/Games"
move_into_if_exists "$HOME_DIR/.steampath"  "$HOME_DIR/Games"
move_into_if_exists "$HOME_DIR/.steampid"   "$HOME_DIR/Games"
# if you had some other game-related folders in ~, add them here

echo

# ----------------------------------------
# 4. cloud / sync-related items
# ----------------------------------------
log_doing "organising cloud-related items"
move_into_if_exists "$HOME_DIR/iCloudPhotos" "$HOME_DIR/Cloud"
move_into_if_exists "$HOME_DIR/.pyicloud"    "$HOME_DIR/Cloud"

echo

# ----------------------------------------
# 5. archive stray top-level files (non-dot)
#    here we just handle the extra 'bashrc' copy
# ----------------------------------------
log_doing "archiving miscellaneous items"
if [ -f "$HOME_DIR/bashrc" ]; then
    make_dir "$HOME_DIR/Archive"
    log_action "moving stray bashrc -> Archive/"
    mv -i "$HOME_DIR/bashrc" "$HOME_DIR/Archive/"
else
    log_info "no stray bashrc found (skip)"
fi

echo

# ----------------------------------------
# 6. create convenience config symlinks in ~/Configs
# ----------------------------------------
log_doing "creating convenience config symlinks in ~/Configs"

create_symlink_if_missing() {
    local target="$1"
    local linkname="$2"

    if [ ! -e "$target" ]; then
        log_info "target does not exist (skip link): $target"
        return
    fi

    if [ -L "$linkname" ] || [ -e "$linkname" ]; then
        log_info "link or file already exists (skip): $linkname"
    else
        log_action "creating symlink: $linkname -> $target"
        ln -s "$target" "$linkname"
    fi
}

create_symlink_if_missing "$HOME_DIR/.config" "$HOME_DIR/Configs/config"
create_symlink_if_missing "$HOME_DIR/.local"  "$HOME_DIR/Configs/local"
create_symlink_if_missing "$HOME_DIR/.mozilla" "$HOME_DIR/Configs/mozilla"
create_symlink_if_missing "$HOME_DIR/.cache"  "$HOME_DIR/Configs/cache"

echo
log_done "done. review the changes above to make sure everything looks good."

