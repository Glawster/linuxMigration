#!/usr/bin/env python3
"""
convertJpgToPng.py

Scan a folder (and subfolders) for JPEG files and convert them to PNG format.
After successful conversion, the original JPEG file is deleted to conserve disk space.

Usage:
    python3 convertJpgToPng.py /path/to/folder [--dry-run]
"""

import argparse
import os
import time
from pathlib import Path
from typing import Tuple

from PIL import Image, UnidentifiedImageError


def is_jpeg(path: Path) -> bool:
    """Check if a file is a JPEG based on its extension."""
    return path.suffix.lower() in {".jpg", ".jpeg"}


def convert_image(path: Path, dry_run: bool) -> Tuple[bool, str]:
    """
    Convert a JPEG image to PNG format and delete the original.
    Returns (success, message).
    """
    try:
        # Open and load the image
        img = Image.open(path)
        img.load()
    except UnidentifiedImageError:
        return False, f"SKIP (not a valid image): {path}"
    except Exception as e:
        return False, f"ERROR opening {path}: {e}"

    # Determine output path
    out_path = path.with_suffix(".png")

    # Check if output file already exists
    if out_path.exists():
        return False, f"SKIP (PNG already exists): {path} -> {out_path}"

    if dry_run:
        return True, f"[DRY RUN] would convert: {path} -> {out_path}"

    # Preserve timestamps
    try:
        stat = path.stat()
    except FileNotFoundError:
        stat = None

    try:
        # Convert to RGB if necessary (PNG supports RGB and RGBA)
        if img.mode not in ("RGB", "RGBA", "L", "LA"):
            img = img.convert("RGB")

        # Save as PNG
        img.save(out_path, format="PNG", optimize=True)

        # Restore timestamps to the new PNG file
        if stat is not None:
            os.utime(out_path, (stat.st_atime, stat.st_mtime))

        # Delete the original JPEG file
        path.unlink()

        return True, f"CONVERTED: {path} -> {out_path}"
    except Exception as e:
        # If conversion failed and PNG was created, clean it up
        if out_path.exists():
            try:
                out_path.unlink()
            except Exception:
                pass
        return False, f"ERROR converting {path}: {e}"


def print_progress(current: int, total: int, start_time: float, label: str = "Progress"):
    """Print a progress indicator."""
    if total == 0:
        return
    percent = (current / total) * 100
    elapsed = time.time() - start_time
    if current > 0:
        eta = (elapsed / current) * (total - current)
        eta_str = time.strftime("%H:%M:%S", time.gmtime(eta))
    else:
        eta_str = "??:??:??"
    
    print(f"\r{label}: {current}/{total} ({percent:.1f}%) - ETA: {eta_str}", end="", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Convert JPEG images to PNG format and delete originals."
    )
    parser.add_argument(
        "folder",
        help="Root folder to scan (will recurse into subfolders).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not modify anything, just print what would be done.",
    )

    args = parser.parse_args()
    root = Path(args.folder).expanduser().resolve()

    if not root.is_dir():
        print(f"ERROR: {root} is not a directory.")
        return

    print(f"Scanning: {root}")
    if args.dry_run:
        print("[DRY RUN] No files will be changed.\n")
    else:
        print()

    # Collect all JPEG files
    jpeg_files = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not is_jpeg(path):
            continue
        jpeg_files.append(path)

    total = len(jpeg_files)
    print(f"Found {total} JPEG file(s) to convert\n")

    if total == 0:
        print("No JPEG files found. Nothing to do.")
        return

    converted = 0
    skipped = 0
    errors = 0
    start_time = time.time()

    for idx, path in enumerate(jpeg_files, start=1):
        print_progress(idx, total, start_time, label="Converting")
        
        success, msg = convert_image(path, args.dry_run)
        
        # Print detailed message on new line
        print(f"\r{msg}")
        
        if msg.startswith("ERROR"):
            errors += 1
        elif msg.startswith("SKIP"):
            skipped += 1
        elif success:
            converted += 1

    print()
    print(f"Done. JPEG files found: {total}")
    print(f"Converted: {converted}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")


if __name__ == "__main__":
    main()
