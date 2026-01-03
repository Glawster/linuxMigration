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
import sys
import time
from pathlib import Path
from typing import Tuple

from PIL import Image, UnidentifiedImageError, PngImagePlugin

# Try to import shared utilities if available
try:
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
    Preserves EXIF metadata by converting it to PNG text chunks.
    Returns (success, message).
    """
    # Determine output path
    outPath = path.with_suffix(".png")
    prefix = "...[]" if dryRun else "..."

    # Check if PNG already exists - if so, just delete the JPG
    if outPath.exists():
        if not dryRun:
            try:
                path.unlink()
            except Exception as e:
                return False, f"Error deleting {path}: {e}"
        return True, f"{prefix} deleted jpg (png exists): {path}"

    try:
        # Open and load the image
        img = Image.open(path)
        img.load()
    except UnidentifiedImageError:
        return False, f"...skip (not a valid image): {path}"
    except Exception as e:
        return False, f"Error opening {path}: {e}"

    # Preserve timestamps
    try:
        stat = path.stat()
    except FileNotFoundError:
        stat = None

    if not dryRun:
        try:
            # Convert to RGB if necessary (PNG supports RGB and RGBA)
            if img.mode not in ("RGB", "RGBA", "L", "LA"):
                img = img.convert("RGB")

            # Extract and preserve EXIF metadata
            pngInfo = PngImagePlugin.PngInfo()
            
            # Try to get EXIF data from the JPEG
            try:
                exif = img.getexif()
                if exif:
                    # Convert EXIF data to PNG text chunks
                    for tag, value in exif.items():
                        try:
                            # Convert tag to string and value to string representation
                            pngInfo.add_text(f"exif:{tag}", str(value))
                        except Exception:
                            # Skip tags that can't be converted
                            pass
            except AttributeError:
                # Fallback for older Pillow versions
                try:
                    exif = img._getexif()
                    if exif:
                        for tag, value in exif.items():
                            try:
                                pngInfo.add_text(f"exif:{tag}", str(value))
                            except Exception:
                                pass
                except Exception:
                    # No EXIF data available
                    pass
            except Exception:
                # Failed to read EXIF, continue without it
                pass

            # Also preserve any other metadata
            if hasattr(img, 'info'):
                for key, value in img.info.items():
                    if key not in ('exif', 'jfif', 'jfif_version', 'jfif_unit', 
                                   'jfif_density', 'dpi', 'adobe', 'adobe_transform'):
                        try:
                            pngInfo.add_text(str(key), str(value))
                        except Exception:
                            pass

            # Save as PNG with metadata
            img.save(outPath, format="PNG", pnginfo=pngInfo, optimize=True)

            # Restore timestamps to the new PNG file
            if stat is not None:
                os.utime(outPath, (stat.st_atime, stat.st_mtime))

            # Delete the original JPEG file
            path.unlink()

        except Exception as e:
            # If conversion failed and PNG was created, clean it up
            if outPath.exists():
                try:
                    outPath.unlink()
                except Exception:
                    pass
            return False, f"Error converting {path}: {e}"

    return True, f"{prefix} converted: {path} -> {outPath}"


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
        dest="dryRun",
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

    try:
        root = Path(args.folder).expanduser().resolve()
    except Exception as e:
        logger.error(f"Error resolving folder path: {e}")
        return 1

    if not root.is_dir():
        logger.error(f"{root} is not a directory.")
        return 1

    logger.info(f"...scanning: {root}")
    prefix = "...[]" if args.dryRun else "..."
    if args.dryRun:
        logger.info(f"{prefix} no files will be changed.")

    # Collect all JPEG files
    jpegFiles = []
    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if not isJpeg(path):
                continue
            jpegFiles.append(path)
    except Exception as e:
        logger.error(f"Error scanning directory: {e}")
        return 1

    total = len(jpegFiles)
    logger.info(f"...found {total} jpeg file(s) to convert")

    if total == 0:
        logger.info("...no jpeg files found. nothing to do.")
        return 0

    converted = 0
    deleted = 0
    skipped = 0
    errors = 0
    startTime = time.time()

    for idx, path in enumerate(jpegFiles, start=1):
        printProgress(idx, total, startTime, label="Converting")

        success, msg = convertImage(path, args.dryRun, logger)

        # Log detailed message
        print()  # Clear progress line
        if msg.startswith("Error"):
            logger.error(msg)
            errors += 1
        elif msg.startswith("...skip"):
            logger.debug(msg)
            skipped += 1
        elif "deleted jpg" in msg:
            logger.info(msg)
            deleted += 1
        elif success:
            logger.info(msg)
            converted += 1

    print()  # Final newline after progress
    logger.info(f"...conversion complete")
    logger.info(f"...jpeg files found: {total}")
    logger.info(f"...converted: {converted}, deleted (png exists): {deleted}, skipped: {skipped}, errors: {errors}")
    
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n...interrupted by user")
        exit(130)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        exit(1)
