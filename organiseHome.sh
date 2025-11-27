#!/usr/bin/env bash
set -euo pipefail

HOME_DIR="$HOME"

echo "=== organising $HOME_DIR ==="

# ----------------------------------------
# helper: make directory if it doesn't exist
# ----------------------------------------
make_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo "creating directory: $dir"
        mkdir -p "$dir"
    else
        echo "directory already exists: $dir"
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
        echo "moving $src -> $target_dir"
        mv -i "$src" "$target_dir/"
    else
        echo "not found (skip): $src"
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
echo "=== organising development-related items ==="
move_into_if_exists "$HOME_DIR/.vscode"     "$HOME_DIR/Development"
move_into_if_exists "$HOME_DIR/.conda"      "$HOME_DIR/Development"
move_into_if_exists "$HOME_DIR/miniconda3"  "$HOME_DIR/Development"

echo

# ----------------------------------------
# 3. gaming-related items
# ----------------------------------------
echo "=== organising gaming-related items ==="
# note: there is already a ~/Games directory; we just gather game stuff into it
move_into_if_exists "$HOME_DIR/.steam"      "$HOME_DIR/Games"
move_into_if_exists "$HOME_DIR/.steampath"  "$HOME_DIR/Games"
move_into_if_exists "$HOME_DIR/.steampid"   "$HOME_DIR/Games"
# if you had some other game-related folders in ~, add them here

echo

# ----------------------------------------
# 4. cloud / sync-related items
# ----------------------------------------
echo "=== organising cloud-related items ==="
move_into_if_exists "$HOME_DIR/iCloudPhotos" "$HOME_DIR/Cloud"
move_into_if_exists "$HOME_DIR/.pyicloud"    "$HOME_DIR/Cloud"

echo

# ----------------------------------------
# 5. archive stray top-level files (non-dot)
#    here we just handle the extra 'bashrc' copy
# ----------------------------------------
echo "=== archiving miscellaneous items ==="
if [ -f "$HOME_DIR/bashrc" ]; then
    make_dir "$HOME_DIR/Archive"
    echo "moving stray bashrc -> Archive/"
    mv -i "$HOME_DIR/bashrc" "$HOME_DIR/Archive/"
else
    echo "no stray bashrc found (skip)"
fi

echo

# ----------------------------------------
# 6. create convenience config symlinks in ~/Configs
# ----------------------------------------
echo "=== creating convenience config symlinks in ~/Configs ==="

create_symlink_if_missing() {
    local target="$1"
    local linkname="$2"

    if [ ! -e "$target" ]; then
        echo "target does not exist (skip link): $target"
        return
    fi

    if [ -L "$linkname" ] || [ -e "$linkname" ]; then
        echo "link or file already exists (skip): $linkname"
    else
        echo "creating symlink: $linkname -> $target"
        ln -s "$target" "$linkname"
    fi
}

create_symlink_if_missing "$HOME_DIR/.config" "$HOME_DIR/Configs/config"
create_symlink_if_missing "$HOME_DIR/.local"  "$HOME_DIR/Configs/local"
create_symlink_if_missing "$HOME_DIR/.mozilla" "$HOME_DIR/Configs/mozilla"
create_symlink_if_missing "$HOME_DIR/.cache"  "$HOME_DIR/Configs/cache"

echo
echo "=== done. review the changes above to make sure everything looks good. ==="

