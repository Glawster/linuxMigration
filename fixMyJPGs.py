#!/usr/bin/env python3
"""
fixMyJPGs.py

Scan a folder (and subfolders) for JPEG files and re-save them in a
DaVinci-Resolve-friendly format:

- sRGB
- baseline (non-progressive)
- 4:2:0 subsampling
- EXIF & weird metadata stripped

By default it overwrites files *in place* while preserving timestamps.
Use --suffix to write new files instead.
Use --dry-run to only print what would be done.
"""

import argparse
import os
from pathlib import Path
from typing import Tuple

from PIL import Image, UnidentifiedImageError


def is_jpeg(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg"}


def process_image(path: Path, overwrite: bool, suffix: str, dry_run: bool) -> Tuple[bool, str]:
    """
    Returns (changed, message)
    """
    try:
        img = Image.open(path)
        img.load()
    except UnidentifiedImageError:
        return False, f"SKIP (not a valid image?): {path}"
    except Exception as e:
        return False, f"ERROR opening {path}: {e}"

    # Decide output path
    if overwrite and not suffix:
        out_path = path
    else:
        # add suffix before extension
        out_path = path.with_name(path.stem + suffix + path.suffix)

    # Only "fix" JPEGs; Pillow will convert modes if needed
    # We treat anything not plain RGB as suspicious and normalise it.
    needs_fix = img.mode != "RGB" or getattr(img, "info", {}).get("progression", False)

    # To be safe, we just normalise all JPEGs; it's cheap and most robust.
    needs_fix = True

    if not needs_fix:
        return False, f"OK (no change): {path}"

    if dry_run:
        return True, f"[] would fix: {path} -> {out_path}"

    # Preserve timestamps
    try:
        stat = path.stat()
    except FileNotFoundError:
        stat = None

    # Normalise
    try:
        img = img.convert("RGB")

        # Strip metadata by not passing img.info
        img.save(
            out_path,
            format="JPEG",
            quality=95,
            subsampling="4:2:0",
            optimize=True,
            progressive=False,
        )

        # If overwriting, make sure original path is replaced
        if out_path != path and overwrite:
            path.unlink()
            out_path.rename(path)
            out_path = path

        # Restore timestamps
        if stat is not None:
            os.utime(out_path, (stat.st_atime, stat.st_mtime))

        return True, f"FIXED: {path}"
    except Exception as e:
        return False, f"ERROR saving {path}: {e}"


def main():
    parser = argparse.ArgumentParser(description="Clean AI / problematic JPEGs for DaVinci Resolve.")
    parser.add_argument(
        "root",
        help="Root folder to scan (will recurse into subfolders).",
    )
    parser.add_argument(
        "--suffix",
        default="",
        help="Suffix to add before extension instead of overwriting (e.g. _fixed). "
             "If empty (default), files are overwritten in place.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify anything, just print what would be done.",
    )

    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()

    if not root.is_dir():
        print(f"ERROR: {root} is not a directory.")
        return

    overwrite = args.suffix == ""
    suffix = args.suffix

    print(f"Scanning: {root}")
    print(f"Overwrite in place: {overwrite}")
    if suffix:
        print(f"Using suffix: {suffix}")
    if args.dry_run:
        print("DRY RUN mode - no files will be changed.")
    print()

    total = 0
    fixed = 0
    skipped = 0
    errors = 0

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not is_jpeg(path):
            continue

        total += 1
        changed, msg = process_image(path, overwrite=overwrite, suffix=suffix, dry_run=args.dry_run)
        print(msg)
        if msg.startswith("FIXED") or msg.startswith("[] would fix"):
            fixed += 1
        elif msg.startswith("SKIP"):
            skipped += 1
        elif msg.startswith("ERROR"):
            errors += 1

    print()
    print(f"Done. JPEG files seen: {total}")
    print(f"Fixed: {fixed}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()

