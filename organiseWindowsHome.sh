#!/usr/bin/env bash
set -euo pipefail

DOCS_DIR="$HOME/Documents"     # symlink to /mnt/home/Andy/Documents
WIN_ARCHIVE="$DOCS_DIR/WindowsArchive"

echo "=== organising Windows home under: $DOCS_DIR ==="

# ensure Documents exists
if [ ! -d "$DOCS_DIR" ]; then
    echo "ERROR: $DOCS_DIR not found."
    exit 1
fi

# create WindowsArchive
if [ ! -d "$WIN_ARCHIVE" ]; then
    echo "creating archive directory: $WIN_ARCHIVE"
    mkdir -p "$WIN_ARCHIVE"
else
    echo "archive exists: $WIN_ARCHIVE"
fi

echo
echo "=== removing Windows-era symlinks (My Music/Pictures/Videos) ==="

for link in "My Music" "My Pictures" "My Videos"; do
    if [ -L "$DOCS_DIR/$link" ]; then
        echo "removing symlink: $DOCS_DIR/$link"
        rm "$DOCS_DIR/$link"
    else
        echo "symlink not found (skip): $DOCS_DIR/$link"
    fi
done

echo
echo "=== moving Windows items except 'my...' into WindowsArchive ==="

shopt -s dotglob nullglob
for item in "$DOCS_DIR"/*; do
    base="$(basename "$item")"

    # skip archive
    if [ "$base" = "windowsArchive" ]; then
        echo "skip archive dir: $base"
        continue
    fi

    # preserve any filename starting with my or My
    case "$base" in
        my*|My*|office*)
            echo "keep at top-level: $base"
            continue
            ;;
    esac

    echo "moving: $base -> WindowsArchive/"
    mv -i "$item" "$WIN_ARCHIVE/"
done
shopt -u dotglob nullglob

echo
echo "=== completed. top-level 'my...' kept, everything else archived. ==="

