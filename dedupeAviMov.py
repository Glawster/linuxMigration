#!/usr/bin/env python3
"""
dedupeAviMov.py

Compare pairs of .avi and .mov files that share the same base name and move the
inferior copy to an AviMovDuplicates/ sub-folder inside the source directory.

For each matched pair the script:
  1. Reads duration and pixel dimensions from both files via ffprobe.
  2. Skips the pair if the durations differ by more than DURATION_TOLERANCE
     seconds (different content).
  3. Extracts a sample frame from each file and compares them with a
     perceptual hash (requires Pillow + imagehash).  Skips the pair if the
     frames look different.
  4. Decides which copy is inferior:
       - Lower pixel count  →  inferior
       - Same pixel count   →  larger file size is inferior
  5. Moves the inferior copy to AviMovDuplicates/.

By default this is a dry-run and only reports what would be done.
Pass --confirm to actually move files.

Requirements:
    pip install Pillow imagehash
    (ffprobe and ffmpeg must be on PATH)

Usage:
    python3 dedupeAviMov.py [--source PATH] [--confirm]

Examples:
    python3 dedupeAviMov.py --source ~/Videos/FionaCooper
    python3 dedupeAviMov.py --source ~/Videos/FionaCooper --confirm
    python3 dedupeAviMov.py --source ~/Videos/FionaCooper -c
"""

import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from PIL import Image
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

# Perceptual-hash distance threshold (0 = pixel-perfect match; ≤8 = visually same)
PHASH_THRESHOLD = 8

# Duration tolerance in seconds – clips are "same content" if durations differ
# by no more than this amount
DURATION_TOLERANCE = 2.0


# ---------------------------------------------------------------------------
# ffprobe helpers
# ---------------------------------------------------------------------------

def getVideoInfo(path: Path) -> Optional[dict]:
    """
    Return basic video metadata via ffprobe.

    Returns a dict with keys: duration (float, seconds), width (int), height (int),
    size (int, bytes).  Returns None if ffprobe fails or the file is not a video.
    """
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "stream=width,height:format=duration,size",
            str(path),
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        data = json.loads(out)

        width = height = None
        for stream in data.get("streams", []):
            if stream.get("width") and stream.get("height"):
                width = int(stream["width"])
                height = int(stream["height"])
                break

        fmt = data.get("format", {})
        duration = float(fmt["duration"]) if fmt.get("duration") else None
        size = int(fmt["size"]) if fmt.get("size") else path.stat().st_size

        return {"duration": duration, "width": width, "height": height, "size": size}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Thumbnail helpers
# ---------------------------------------------------------------------------

def extractThumbnail(videoPath: Path, outDir: Path, timestamp: float) -> Optional[Path]:
    """
    Extract one frame at *timestamp* seconds from *videoPath* and save it as PNG
    in *outDir*.  Returns the Path to the PNG, or None on failure.
    """
    thumbPath = outDir / f"{videoPath.stem}_{int(timestamp * 1000)}.png"
    try:
        cmd = [
            "ffmpeg",
            "-ss", str(timestamp),
            "-i", str(videoPath),
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            str(thumbPath),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if thumbPath.exists() and thumbPath.stat().st_size > 0:
            return thumbPath
    except Exception:
        pass
    return None


def compareFrames(img1: Path, img2: Path) -> Optional[int]:
    """
    Return the perceptual-hash distance between two images (0 = identical).
    Returns None if comparison is not possible.
    """
    if not IMAGEHASH_AVAILABLE:
        return None
    try:
        with Image.open(img1) as i1, Image.open(img2) as i2:
            return int(imagehash.phash(i1) - imagehash.phash(i2))
    except Exception:
        return None


def thumbnailsMatch(aviPath: Path, movPath: Path, duration: float, tmpDir: Path) -> Optional[bool]:
    """
    Extract a frame at ~10 % of the video length and compare both files.

    Returns True if they look the same, False if they look different, or None
    when the comparison could not be performed (missing tools / short clip).
    """
    if not IMAGEHASH_AVAILABLE:
        return None
    if duration is None or duration < 1.0:
        return None

    sampleTime = max(1.0, duration * 0.1)
    thumb1 = extractThumbnail(aviPath, tmpDir, sampleTime)
    thumb2 = extractThumbnail(movPath, tmpDir, sampleTime)
    if not thumb1 or not thumb2:
        return None

    dist = compareFrames(thumb1, thumb2)
    if dist is None:
        return None

    return dist <= PHASH_THRESHOLD


# ---------------------------------------------------------------------------
# Pair discovery and decision logic
# ---------------------------------------------------------------------------

def findPairs(sourceDir: Path) -> List[Tuple[Path, Path]]:
    """
    Return a sorted list of (aviPath, movPath) tuples for all files in
    *sourceDir* whose stems match (case-insensitive) and whose extensions are
    .avi and .mov respectively.

    Only the top level of *sourceDir* is searched (not recursive) because the
    user described a single working folder.
    """
    avis: dict[str, Path] = {}
    movs: dict[str, Path] = {}

    for f in sourceDir.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        key = f.stem.lower()
        if ext == ".avi":
            avis[key] = f
        elif ext == ".mov":
            movs[key] = f

    pairs = [
        (avis[key], movs[key])
        for key in sorted(avis)
        if key in movs
    ]
    return pairs


def decideSurvivor(
    aviPath: Path,
    movPath: Path,
    aviInfo: dict,
    movInfo: dict,
) -> Tuple[Optional[Path], str]:
    """
    Decide which file is inferior and should be removed.

    Returns (pathToRemove, reason_string).
    Returns (None, reason_string) when no decision can be made.
    """
    aviPixels = (aviInfo["width"] or 0) * (aviInfo["height"] or 0)
    movPixels = (movInfo["width"] or 0) * (movInfo["height"] or 0)

    if aviPixels != movPixels:
        if aviPixels > movPixels:
            return movPath, (
                f"avi is higher resolution "
                f"({aviInfo['width']}x{aviInfo['height']} vs "
                f"{movInfo['width']}x{movInfo['height']})"
            )
        return aviPath, (
            f"mov is higher resolution "
            f"({movInfo['width']}x{movInfo['height']} vs "
            f"{aviInfo['width']}x{aviInfo['height']})"
        )

    # Same (or unknown) resolution – remove the larger file
    if aviInfo["size"] > movInfo["size"]:
        return aviPath, (
            f"same resolution, avi is larger "
            f"({aviInfo['size']:,} vs {movInfo['size']:,} bytes)"
        )
    if movInfo["size"] > aviInfo["size"]:
        return movPath, (
            f"same resolution, mov is larger "
            f"({movInfo['size']:,} vs {aviInfo['size']:,} bytes)"
        )

    return None, "files appear identical in resolution and size"


def safeMove(src: Path, dstDir: Path) -> Path:
    """Move *src* into *dstDir*, appending a counter to avoid name collisions."""
    dstDir.mkdir(parents=True, exist_ok=True)
    target = dstDir / src.name
    i = 1
    while target.exists():
        target = dstDir / f"{src.stem}_{i}{src.suffix}"
        i += 1
    src.rename(target)
    return target


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def processPairs(sourceDir: Path, confirm: bool) -> None:
    """Scan *sourceDir* for .avi/.mov pairs and handle inferior copies."""
    pairs = findPairs(sourceDir)

    if not pairs:
        print("No .avi/.mov pairs found.")
        return

    print(f"Found {len(pairs)} .avi/.mov pair(s) to compare.\n")

    if not IMAGEHASH_AVAILABLE:
        print(
            "NOTE: Pillow / imagehash not found – thumbnail comparison disabled.\n"
            "      Install with: pip install Pillow imagehash\n"
        )

    dupesDir = sourceDir / "AviMovDuplicates"

    toRemove: List[Tuple[Path, str]] = []
    skipped: List[Tuple[Path, Path, str]] = []
    errors: List[Tuple[Path, Path, str]] = []

    with tempfile.TemporaryDirectory() as tmpDir:
        tmpPath = Path(tmpDir)

        for aviPath, movPath in pairs:
            print(f"  Pair: {aviPath.name}  |  {movPath.name}")

            aviInfo = getVideoInfo(aviPath)
            movInfo = getVideoInfo(movPath)

            if aviInfo is None or movInfo is None:
                msg = "could not read video info via ffprobe"
                print(f"    SKIP: {msg}\n")
                errors.append((aviPath, movPath, msg))
                continue

            # --- Duration check ---
            aviDur = aviInfo["duration"] or 0.0
            movDur = movInfo["duration"] or 0.0
            durDiff = abs(aviDur - movDur)

            if durDiff > DURATION_TOLERANCE:
                msg = (
                    f"duration mismatch "
                    f"(avi={aviDur:.1f}s, mov={movDur:.1f}s, diff={durDiff:.1f}s)"
                )
                print(f"    SKIP: {msg}\n")
                skipped.append((aviPath, movPath, msg))
                continue

            # --- Thumbnail comparison ---
            minDur = min(aviDur, movDur)
            match = thumbnailsMatch(aviPath, movPath, minDur, tmpPath)

            if match is False:
                msg = "thumbnail perceptual-hash mismatch – files look different"
                print(f"    SKIP: {msg}\n")
                skipped.append((aviPath, movPath, msg))
                continue

            if match is True:
                print("    Thumbnails match.")
            else:
                print("    Thumbnail comparison skipped (tool unavailable).")

            # --- Decide which to remove ---
            pathToRemove, reason = decideSurvivor(aviPath, movPath, aviInfo, movInfo)

            if pathToRemove is None:
                print(f"    INFO: {reason} – nothing to do.\n")
                skipped.append((aviPath, movPath, reason))
                continue

            pathToKeep = movPath if pathToRemove == aviPath else aviPath
            print(f"    REMOVE: {pathToRemove.name}  ({reason})")
            print(f"    KEEP:   {pathToKeep.name}\n")
            toRemove.append((pathToRemove, reason))

    print("-" * 60)
    print(
        f"Summary: {len(toRemove)} to remove, "
        f"{len(skipped)} skipped, {len(errors)} error(s).\n"
    )

    if not toRemove:
        print("Nothing to do.")
        return

    if not confirm:
        print("=" * 60)
        print("DRY RUN – no files have been moved.")
        print(f"Files that would be moved to {dupesDir.name}/:")
        for p, reason in toRemove:
            print(f"  {p.name}  ({reason})")
        print()
        print("To actually move the files, run with --confirm:")
        print("    python3 dedupeAviMov.py --confirm --source <path>")
        print("=" * 60)
        return

    # --- Confirmed ---
    print("=" * 60)
    print(f"CONFIRMED – moving inferior copies to {dupesDir.name}/ ...")
    print("=" * 60)
    moved = 0
    for p, reason in toRemove:
        try:
            dest = safeMove(p, dupesDir)
            print(f"  Moved: {p.name}  ->  {dest}")
            moved += 1
        except Exception as e:
            print(f"  ERROR moving {p.name}: {e}")

    print()
    print(f"Done: {moved} file(s) moved to {dupesDir}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def sourceDirPath(value: str) -> str:
    """Validate --source argument and return resolved path string."""
    try:
        p = Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"Error resolving path '{value}': {e}")
    if not p.exists():
        raise argparse.ArgumentTypeError(f"Directory does not exist: {p}")
    if not p.is_dir():
        raise argparse.ArgumentTypeError(f"Not a directory: {p}")
    return str(p)


def parseArgs():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Compare .avi/.mov pairs that share the same base name and move "
            "the inferior copy to AviMovDuplicates/."
        )
    )
    parser.add_argument(
        "--source",
        type=sourceDirPath,
        default=".",
        help="Directory to scan for .avi/.mov pairs (default: current directory).",
    )
    parser.add_argument(
        "--confirm",
        "-c",
        "--yes",
        action="store_true",
        help="Actually move files.  Without this flag the script is a dry-run.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parseArgs()

    print("AVI / MOV Duplicate Remover")
    print("-" * 60)

    processPairs(Path(args.source), confirm=args.confirm)
