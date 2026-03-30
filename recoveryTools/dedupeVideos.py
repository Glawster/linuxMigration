#!/usr/bin/env python3
"""
dedupeVideos.py

Two modes of video deduplication:

  sha256   – Exact deduplication using SHA-256 hashes.
             Scans recursively, keeps the first-seen copy in place, moves
             duplicates to a VideoDuplicates/ folder inside the source folder.
             Designed to be run AFTER recovery/flattening.

  avi-mov  – Smart deduplication of .avi/.mov pairs sharing the same base
             name.  For each pair the script:
               1. Reads duration and pixel dimensions via ffprobe.
               2. Skips the pair if durations differ by more than
                  DURATION_TOLERANCE seconds (different content).
               3. Extracts a sample frame from each file and compares them
                  with a perceptual hash (requires Pillow + imagehash).
                  Skips the pair if the frames look different.
               4. Decides which copy is inferior:
                    - Lower pixel count  →  inferior
                    - Same pixel count   →  larger file size is inferior
               5. Moves the inferior copy to AviMovDuplicates/.

Both modes default to a dry-run; pass --confirm / -c to actually move files.

Requirements:
    pip install Pillow imagehash
    (ffprobe and ffmpeg must be on PATH for avi-mov mode)

Usage:
    python3 dedupeVideos.py sha256  --source <path> [--confirm]
    python3 dedupeVideos.py avi-mov --source <path> [--confirm]

Examples:
    python3 dedupeVideos.py sha256  --source ~/Videos/Recovery
    python3 dedupeVideos.py sha256  --source ~/Videos/Recovery --confirm
    python3 dedupeVideos.py avi-mov --source ~/Videos/FionaCooper
    python3 dedupeVideos.py avi-mov --source ~/Videos/FionaCooper --confirm
    python3 dedupeVideos.py avi-mov --source ~/Videos/FionaCooper -c
"""

import argparse
import hashlib
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from organiseMyProjects.logUtils import getLogger  # type: ignore
from recoveryCommon import isVideo, printProgress

logger = getLogger("dedupeVideos")

try:
    from PIL import Image
    import imagehash
    IMAGEHASH_AVAILABLE = True
except ImportError:
    IMAGEHASH_AVAILABLE = False

# Perceptual-hash distance threshold (0 = pixel-perfect; <=8 = visually same)
PHASH_THRESHOLD = 8

# Duration tolerance in seconds – clips are "same content" if they differ
# by no more than this amount
DURATION_TOLERANCE = 2.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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


def sourceDirPath(value: str) -> str:
    """Validate --source argument and return the resolved path string."""
    try:
        p = Path(value).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"Error resolving path '{value}': {e}")
    if not p.exists():
        raise argparse.ArgumentTypeError(f"Directory does not exist: {p}")
    if not p.is_dir():
        raise argparse.ArgumentTypeError(f"Not a directory: {p}")
    return str(p)


# ---------------------------------------------------------------------------
# sha256 mode
# ---------------------------------------------------------------------------

def hashFile(path: Path, chunkSize: int = 1024 * 1024) -> str:
    """Return the SHA-256 hex digest of *path*."""
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunkSize)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def runSha256(sourceDir: Path, confirm: bool, logger: logging.LoggerAdapter) -> None:
    """Exact-dedup all video files under *sourceDir* by SHA-256."""
    dryRun = not confirm
    dupesDir = sourceDir / "VideoDuplicates"

    logger.doing(f"scanning {sourceDir} for duplicate videos")
    videos = [p for p in sourceDir.rglob("*") if p.is_file() and isVideo(p)]
    total = len(videos)
    logger.info("found %d video file(s) to dedupe", total)

    seen: Dict[str, Path] = {}
    kept = moved = errors = 0
    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Dedupe videos")

    for v in videos:
        done += 1
        printProgress(done, total, startTime, label="Dedupe videos")

        try:
            h = hashFile(v)
        except Exception as e:
            errors += 1
            logger.error("Hash failed for %s: %s", str(v), str(e))
            continue

        if h not in seen:
            seen[h] = v
            kept += 1
            continue

        # duplicate found
        logger.action(f"move: {v}  (dup of {seen[h]})")
        moved += 1
        if confirm:
            try:
                dst = safeMove(v, dupesDir)
                logger.done(f"moved to: {dst}")
            except Exception as e:
                moved -= 1
                errors += 1
                logger.error("Move failed for %s: %s", v.name, str(e))

    print()  # finish the progress bar line
    logger.done(f"summary: total={total}  kept={kept}  moved={moved}  errors={errors}")
    if dryRun and moved:
        logger.info("to actually move files, run with --confirm")


# ---------------------------------------------------------------------------
# avi-mov mode – ffprobe helpers
# ---------------------------------------------------------------------------

def getVideoInfo(path: Path) -> Optional[dict]:
    """
    Return basic video metadata via ffprobe.

    Returns a dict with keys: duration (float, seconds), width (int),
    height (int), size (int, bytes).  Returns None if ffprobe fails.
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


def extractThumbnail(videoPath: Path, outDir: Path, timestamp: float) -> Optional[Path]:
    """
    Extract one frame at *timestamp* seconds from *videoPath* and save as PNG
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


def thumbnailsMatch(
    aviPath: Path, movPath: Path, duration: float, tmpDir: Path
) -> Optional[bool]:
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
# avi-mov mode – pair discovery and decision logic
# ---------------------------------------------------------------------------

def findPairs(sourceDir: Path) -> List[Tuple[Path, Path]]:
    """
    Return a sorted list of (aviPath, movPath) tuples for all files found
    recursively under *sourceDir* whose stems match (case-insensitive) and
    whose extensions are .avi and .mov respectively.  Only files sharing the
    same parent directory are paired.
    """
    avis: Dict[Tuple[Path, str], Path] = {}
    movs: Dict[Tuple[Path, str], Path] = {}

    for f in sourceDir.rglob("*"):
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        key = (f.parent, f.stem.lower())
        if ext == ".avi":
            avis[key] = f
        elif ext == ".mov":
            movs[key] = f

    return [
        (avis[key], movs[key])
        for key in sorted(avis)
        if key in movs
    ]


def decideSurvivor(
    aviPath: Path,
    movPath: Path,
    aviInfo: dict,
    movInfo: dict,
) -> Tuple[Optional[Path], str]:
    """
    Decide which file is inferior and should be moved.

    Returns (pathToRemove, reason_string), or (None, reason_string) when no
    decision can be made.
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


def runAviMov(sourceDir: Path, confirm: bool, logger: logging.LoggerAdapter) -> None:
    """Scan *sourceDir* for .avi/.mov pairs and move the inferior copy."""
    dryRun = not confirm

    logger.doing(f"scanning {sourceDir} for .avi/.mov pairs")
    pairs = findPairs(sourceDir)

    if not pairs:
        logger.done("no .avi/.mov pairs found")
        return

    logger.info("found %d .avi/.mov pair(s) to compare", len(pairs))

    if not IMAGEHASH_AVAILABLE:
        logger.info(
            "Pillow / imagehash not found – thumbnail comparison disabled"
            " (install with: pip install Pillow imagehash)"
        )

    dupesDir = sourceDir / "AviMovDuplicates"

    toRemove: List[Tuple[Path, str]] = []
    skipped: List[Tuple[Path, Path, str]] = []
    errors: List[Tuple[Path, Path, str]] = []

    with tempfile.TemporaryDirectory() as tmpDir:
        tmpPath = Path(tmpDir)

        for aviPath, movPath in pairs:
            logger.doing(f"checking: {aviPath.name}  |  {movPath.name}")

            aviInfo = getVideoInfo(aviPath)
            movInfo = getVideoInfo(movPath)

            if aviInfo is None or movInfo is None:
                msg = "could not read video info via ffprobe"
                logger.error("Skipping pair – %s: %s / %s", msg, aviPath.name, movPath.name)
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
                logger.info("skipping pair – %s: %s", aviPath.name, msg)
                skipped.append((aviPath, movPath, msg))
                continue

            # --- Thumbnail comparison ---
            minDur = min(aviDur, movDur)
            match = thumbnailsMatch(aviPath, movPath, minDur, tmpPath)

            if match is False:
                msg = "thumbnail perceptual-hash mismatch – files look different"
                logger.info("skipping pair – %s: %s", aviPath.name, msg)
                skipped.append((aviPath, movPath, msg))
                continue

            if match is True:
                logger.info("thumbnails match: %s", aviPath.name)
            else:
                logger.info("thumbnail comparison skipped (tool unavailable): %s", aviPath.name)

            # --- Decide which to remove ---
            pathToRemove, reason = decideSurvivor(aviPath, movPath, aviInfo, movInfo)

            if pathToRemove is None:
                logger.info("nothing to do – %s: %s", aviPath.name, reason)
                skipped.append((aviPath, movPath, reason))
                continue

            pathToKeep = movPath if pathToRemove == aviPath else aviPath
            logger.value("will remove", f"{pathToRemove.name}  ({reason})")
            logger.value("will keep", pathToKeep.name)
            toRemove.append((pathToRemove, reason))

    logger.done(
        f"summary: {len(toRemove)} to remove, {len(skipped)} skipped, {len(errors)} error(s)"
    )

    if not toRemove:
        return

    logger.value("destination folder", str(dupesDir))
    moved = 0
    for p, reason in toRemove:
        logger.action(f"move: {p}  ->  {dupesDir / p.name}  ({reason})")
        if confirm:
            try:
                safeMove(p, dupesDir)
                moved += 1
            except Exception as e:
                logger.error("Move failed for %s: %s", p.name, str(e))

    if confirm:
        logger.done(f"{moved} file(s) moved to {dupesDir}")
    else:
        logger.info("to actually move files, run with --confirm")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parseArgs():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Deduplicate video files (SHA-256 exact or AVI/MOV pair comparison)."
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    # --- sha256 sub-command ---
    sha256Parser = subparsers.add_parser(
        "sha256",
        help="Exact deduplication using SHA-256 (recursive).",
    )
    sha256Parser.add_argument(
        "--source",
        type=sourceDirPath,
        default="/mnt/games1/Recovery/Videos",
        help="Source folder containing videos (default: /mnt/games1/Recovery/Videos).",
    )
    sha256Parser.add_argument(
        "--confirm", "-c",
        action="store_true",
        help="Actually move files.  Without this flag the script is a dry-run.",
    )

    # --- avi-mov sub-command ---
    aviMovParser = subparsers.add_parser(
        "avi-mov",
        help="Smart deduplication of .avi/.mov pairs by duration, thumbnail, and resolution.",
    )
    aviMovParser.add_argument(
        "--source",
        type=sourceDirPath,
        default=".",
        help="Directory to scan for .avi/.mov pairs (default: current directory).",
    )
    aviMovParser.add_argument(
        "--confirm", "-c",
        action="store_true",
        help="Actually move files.  Without this flag the script is a dry-run.",
    )

    return parser.parse_args()


def main() -> None:
    """Entry point: parse args, initialise logger, and dispatch to the chosen mode."""
    args = parseArgs()
    dryRun = not args.confirm

    logger = getLogger("dedupeVideos", includeConsole=True, dryRun=dryRun)

    sourceDir = Path(args.source)

    logger.doing("dedupeVideos")
    logger.value("source", str(sourceDir))
    logger.value("mode", args.mode)
    logger.value("dry run", str(dryRun))

    if args.mode == "sha256":
        runSha256(sourceDir, confirm=args.confirm, logger=logger)
    else:
        runAviMov(sourceDir, confirm=args.confirm, logger=logger)


if __name__ == "__main__":
    main()
