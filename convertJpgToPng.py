#!/usr/bin/env python3
"""
convertJpgToPng.py

Scan a folder (and subfolders) for JPEG files and convert them to PNG format.
After successful conversion, the original JPEG file is deleted to conserve disk space.

Usage:
    python3 convertJpgToPng.py /path/to/folder [--dry-run]
"""

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Tuple

from PIL import Image, UnidentifiedImageError

# Try to import shared utilities if available
try:
    import sys
    sys.path.insert(0, str(Path(__file__).parent / "recoveryTools"))
    from recoveryCommon import printProgress
except ImportError:
    # Fallback implementation if recoveryCommon is not available
    def formatEta(seconds: float) -> str:
        if seconds <= 0 or seconds != seconds:
            return "--:--:--"
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        if h > 99:
            return "99:59:59"
        return f"{h:02d}:{m:02d}:{s:02d}"

    def printProgress(
        done: int,
        total: int,
        startTime: float,
        *,
        width: int = 40,
        label: str = "Progress",
    ):
        if total <= 0:
            return
        ratio = min(done / total, 1.0)
        filled = int(width * ratio)
        bar = "#" * filled + "-" * (width - filled)
        pct = int(ratio * 100)
        elapsed = time.time() - startTime
        remaining = ((total - done) * elapsed / done) if done > 0 else 0
        etaStr = formatEta(remaining)
        print(
            f"\r{label}: [{bar}] {pct:3d}% ({done}/{total}) ETA {etaStr}",
            end="",
            flush=True,
        )


def isJpeg(path: Path) -> bool:
    """Check if a file is a JPEG based on its extension."""
    return path.suffix.lower() in {".jpg", ".jpeg"}


def convertImage(path: Path, dryRun: bool, logger: logging.Logger) -> Tuple[bool, str]:
    """
    Convert a JPEG image to PNG format and delete the original.
    Returns (success, message).
    """
    # Determine output path
    outPath = path.with_suffix(".png")

    # Check if PNG already exists - if so, just delete the JPG
    if outPath.exists():
        if dryRun:
            return True, f"[DRY RUN] would delete JPG (PNG exists): {path}"
        else:
            try:
                path.unlink()
                return True, f"DELETED JPG (PNG exists): {path}"
            except Exception as e:
                return False, f"ERROR deleting {path}: {e}"

    try:
        # Open and load the image
        img = Image.open(path)
        img.load()
    except UnidentifiedImageError:
        return False, f"SKIP (not a valid image): {path}"
    except Exception as e:
        return False, f"ERROR opening {path}: {e}"

    if dryRun:
        return True, f"[DRY RUN] would convert: {path} -> {outPath}"

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
        img.save(outPath, format="PNG", optimize=True)

        # Restore timestamps to the new PNG file
        if stat is not None:
            os.utime(outPath, (stat.st_atime, stat.st_mtime))

        # Delete the original JPEG file
        path.unlink()

        return True, f"CONVERTED: {path} -> {outPath}"
    except Exception as e:
        # If conversion failed and PNG was created, clean it up
        if outPath.exists():
            try:
                outPath.unlink()
            except Exception:
                pass
        return False, f"ERROR converting {path}: {e}"


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
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging level (default: INFO).",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    root = Path(args.folder).expanduser().resolve()

    if not root.is_dir():
        logger.error(f"{root} is not a directory.")
        return

    logger.info(f"Scanning: {root}")
    if args.dry_run:
        logger.info("[DRY RUN] No files will be changed.")

    # Collect all JPEG files
    jpegFiles = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not isJpeg(path):
            continue
        jpegFiles.append(path)

    total = len(jpegFiles)
    logger.info(f"Found {total} JPEG file(s) to convert")

    if total == 0:
        logger.info("No JPEG files found. Nothing to do.")
        return

    converted = 0
    deleted = 0
    skipped = 0
    errors = 0
    startTime = time.time()

    for idx, path in enumerate(jpegFiles, start=1):
        printProgress(idx, total, startTime, label="Converting")

        success, msg = convertImage(path, args.dry_run, logger)

        # Log detailed message
        print()  # Clear progress line
        if msg.startswith("ERROR"):
            logger.error(msg)
            errors += 1
        elif msg.startswith("SKIP"):
            logger.debug(msg)
            skipped += 1
        elif "DELETED JPG" in msg or "would delete JPG" in msg:
            logger.info(msg)
            deleted += 1
        elif success:
            logger.info(msg)
            converted += 1

    print()  # Final newline after progress
    logger.info(f"Done. JPEG files found: {total}")
    logger.info(f"Converted: {converted}, Deleted (PNG exists): {deleted}, Skipped: {skipped}, Errors: {errors}")


if __name__ == "__main__":
    main()
