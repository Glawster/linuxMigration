#!/usr/bin/env python3
"""
dedupeVideos.py

Two modes of video deduplication:

  sha256   – Exact deduplication using SHA-256 hashes.
             Scans recursively, keeps the first-seen copy in place, moves
             duplicates to a VideoDuplicates/ folder inside the source folder.
             Designed to be run AFTER recovery/flattening.

  avi-mov  – Smart deduplication of same-name video files in the same
                 folder, regardless of extension. For each matching group
                 the script:
                    1. Reads duration and pixel dimensions via ffprobe.
                    2. Skips file comparisons if durations differ by more than
                        DURATION_TOLERANCE seconds (different content).
                    3. Extracts a sample frame from matching candidates and
                        compares them with a perceptual hash
                        (requires Pillow + imagehash).
                        Skips comparisons if the frames look different.
                    4. Decides which copy is inferior within each matching set:
                          - Lower pixel count  -> inferior
                          - Same pixel count   -> larger file size is inferior
                    5. Moves inferior copies to AviMovDuplicates/.

Both modes default to a dry-run; pass --confirm / -c to actually move files.

Requirements:
    pip install Pillow imagehash
    (ffprobe and ffmpeg must be on PATH for same-name mode)

Usage:
    python3 dedupeVideos.py [--sha256] [--source <path>] [--confirm]

Examples:
    python3 dedupeVideos.py
    python3 dedupeVideos.py --source ~/Videos/FionaCooper
    python3 dedupeVideos.py --source ~/Videos/FionaCooper --confirm
    python3 dedupeVideos.py --sha256 --source ~/Videos/Recovery
    python3 dedupeVideos.py --sha256 --source ~/Videos/Recovery --confirm
"""

import argparse
import hashlib
import itertools
import json
import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from organiseMyProjects.logUtils import drawBox, getLogger, thisApplication  # type: ignore
from recoveryCommon import isVideo, printProgress

thisApplication = Path(__file__).stem
logger = getLogger(thisApplication, includeConsole=True)

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


def formatBytes(numBytes: int) -> str:
    """Return a human-readable binary size string for *numBytes*."""
    value = float(max(numBytes, 0))
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024.0
    return f"{int(value)} B"


def logSummaryBox(
    mode: str,
    dryRun: bool,
    deletedCount: int,
    totalCount: int,
    bytesSaved: int,
    logger: logging.LoggerAdapter,
) -> None:
    """Log a boxed summary with deleted-vs-total and space saved."""
    filesLabel = "files to delete" if dryRun else "files deleted"
    spaceLabel = "potential disk space to save" if dryRun else "disk space saved"
    drawBox(
        "\n".join(
            [
                f"summary ({mode})",
                f"{filesLabel}: {deletedCount}/{totalCount}",
                f"{spaceLabel}: {formatBytes(bytesSaved)} ({bytesSaved:,} bytes)",
            ]
        ),
        logger=logger,
    )


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
    bytesPlanned = 0
    bytesMoved = 0
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
        duplicateSize = 0
        try:
            duplicateSize = v.stat().st_size
        except OSError:
            duplicateSize = 0
        logger.action(f"move: {v}  (dup of {seen[h]})")
        moved += 1
        bytesPlanned += duplicateSize
        if confirm:
            try:
                dst = safeMove(v, dupesDir)
                bytesMoved += duplicateSize
                logger.done(f"moved to: {dst}")
            except Exception as e:
                moved -= 1
                errors += 1
                logger.error("Move failed for %s: %s", v.name, str(e))

    print()  # finish the progress bar line
    logger.done(f"summary: total={total}  kept={kept}  moved={moved}  errors={errors}")
    if dryRun and moved:
        logger.info("to actually move files, run with --confirm")

    deletedCount = moved
    bytesSaved = bytesPlanned if dryRun else bytesMoved
    logSummaryBox("sha256", dryRun, deletedCount, total, bytesSaved, logger)


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
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_entries",
            "stream=width,height:format=duration,size",
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
            "-ss",
            str(timestamp),
            "-i",
            str(videoPath),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            "-y",
            str(thumbPath),
        ]
        subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
        )
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
    firstPath: Path, secondPath: Path, duration: float, tmpDir: Path
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
    thumb1 = extractThumbnail(firstPath, tmpDir, sampleTime)
    thumb2 = extractThumbnail(secondPath, tmpDir, sampleTime)
    if not thumb1 or not thumb2:
        return None

    dist = compareFrames(thumb1, thumb2)
    if dist is None:
        return None

    return dist <= PHASH_THRESHOLD


# ---------------------------------------------------------------------------
# avi-mov mode – same-name group discovery and decision logic
# ---------------------------------------------------------------------------


def findDuplicateGroups(sourceDir: Path) -> List[List[Path]]:
    """
    Return sorted groups of video files found recursively under *sourceDir*
    that share the same parent directory and stem (case-insensitive).
    """
    groups: Dict[Tuple[Path, str], List[Path]] = {}

    for f in sourceDir.rglob("*"):
        if not f.is_file() or not isVideo(f):
            continue
        key = (f.parent, f.stem.lower())
        groups.setdefault(key, []).append(f)

    return [
        sorted(group, key=lambda path: (path.suffix.lower(), path.name.lower()))
        for _, group in sorted(groups.items())
        if len(group) > 1
    ]


def videoQualityKey(path: Path, info: dict) -> Tuple[int, int, str, str]:
    """Return a sort key where lower values represent the preferred survivor."""
    pixels = (info["width"] or 0) * (info["height"] or 0)
    size = int(info["size"] or 0)
    return (-pixels, size, path.suffix.lower(), path.name.lower())


def reasonToRemove(
    removePath: Path, keepPath: Path, removeInfo: dict, keepInfo: dict
) -> str:
    """Explain why *removePath* is inferior to *keepPath*."""
    removePixels = (removeInfo["width"] or 0) * (removeInfo["height"] or 0)
    keepPixels = (keepInfo["width"] or 0) * (keepInfo["height"] or 0)

    if removePixels != keepPixels:
        return (
            f"{keepPath.suffix.lower()} is higher resolution "
            f"({keepInfo['width']}x{keepInfo['height']} vs "
            f"{removeInfo['width']}x{removeInfo['height']})"
        )

    removeSize = int(removeInfo["size"] or 0)
    keepSize = int(keepInfo["size"] or 0)
    if removeSize != keepSize:
        return (
            f"same resolution, {removePath.suffix.lower()} is larger "
            f"({removeSize:,} vs {keepSize:,} bytes)"
        )

    return f"same resolution and size; keeping {keepPath.name} by sort order"


def pairLooksEquivalent(
    firstPath: Path,
    secondPath: Path,
    firstInfo: dict,
    secondInfo: dict,
    tmpPath: Path,
    logger: logging.LoggerAdapter,
) -> bool:
    """Return True when two same-name videos appear to be duplicate content."""
    firstDur = firstInfo["duration"] or 0.0
    secondDur = secondInfo["duration"] or 0.0
    durDiff = abs(firstDur - secondDur)

    if durDiff > DURATION_TOLERANCE:
        logger.info(
            "skipping comparison – %s / %s: duration mismatch "
            "(%ss vs %ss, diff=%ss)",
            firstPath.name,
            secondPath.name,
            f"{firstDur:.1f}",
            f"{secondDur:.1f}",
            f"{durDiff:.1f}",
        )
        return False

    minDur = min(firstDur, secondDur)
    match = thumbnailsMatch(firstPath, secondPath, minDur, tmpPath)
    if match is False:
        logger.info(
            "skipping comparison – %s / %s: thumbnail perceptual-hash mismatch",
            firstPath.name,
            secondPath.name,
        )
        return False

    if match is True:
        logger.info("thumbnails match: %s / %s", firstPath.name, secondPath.name)
    else:
        logger.info(
            "thumbnail comparison skipped (tool unavailable): %s / %s",
            firstPath.name,
            secondPath.name,
        )

    return True


def runAviMov(sourceDir: Path, confirm: bool, logger: logging.LoggerAdapter) -> None:
    """Scan *sourceDir* for same-name video duplication and move inferior copies."""
    dryRun = not confirm
    totalVideos = sum(1 for p in sourceDir.rglob("*") if p.is_file() and isVideo(p))

    logger.doing(f"scanning {sourceDir} for same-name video duplication")
    groups = findDuplicateGroups(sourceDir)

    if not groups:
        logger.done("no duplicates found")
        logSummaryBox("avi-mov", dryRun, 0, totalVideos, 0, logger)
        return

    logger.info("found %d same-name video group(s) to compare", len(groups))

    if not IMAGEHASH_AVAILABLE:
        logger.info(
            "Pillow / imagehash not found – thumbnail comparison disabled"
            " (install with: pip install Pillow imagehash)"
        )

    dupesDir = sourceDir / "AviMovDuplicates"

    toRemove: List[Tuple[Path, str, int]] = []
    skipped: List[str] = []
    errors = 0

    with tempfile.TemporaryDirectory() as tmpDir:
        tmpPath = Path(tmpDir)

        for group in groups:
            displayNames = ", ".join(path.name for path in group)
            logger.doing(f"checking group: {displayNames}")

            infoByPath: Dict[Path, dict] = {}
            readablePaths: List[Path] = []
            for videoPath in group:
                videoInfo = getVideoInfo(videoPath)
                if videoInfo is None:
                    logger.error(
                        "Skipping file – could not read video info via ffprobe: %s",
                        videoPath.name,
                    )
                    errors += 1
                    continue
                infoByPath[videoPath] = videoInfo
                readablePaths.append(videoPath)

            if len(readablePaths) < 2:
                skipped.append(displayNames)
                continue

            parentByPath = {path: path for path in readablePaths}

            def find(path: Path) -> Path:
                while parentByPath[path] != path:
                    parentByPath[path] = parentByPath[parentByPath[path]]
                    path = parentByPath[path]
                return path

            def union(firstPath: Path, secondPath: Path) -> None:
                firstRoot = find(firstPath)
                secondRoot = find(secondPath)
                if firstRoot != secondRoot:
                    parentByPath[secondRoot] = firstRoot

            for firstPath, secondPath in itertools.combinations(readablePaths, 2):
                if pairLooksEquivalent(
                    firstPath,
                    secondPath,
                    infoByPath[firstPath],
                    infoByPath[secondPath],
                    tmpPath,
                    logger,
                ):
                    union(firstPath, secondPath)

            components: Dict[Path, List[Path]] = {}
            for videoPath in readablePaths:
                components.setdefault(find(videoPath), []).append(videoPath)

            matchedComponentFound = False
            for component in components.values():
                if len(component) < 2:
                    continue

                matchedComponentFound = True
                sortedComponent = sorted(
                    component,
                    key=lambda path: videoQualityKey(path, infoByPath[path]),
                )
                keepPath = sortedComponent[0]
                keepInfo = infoByPath[keepPath]
                logger.value("keep", keepPath.name)

                for removePath in sortedComponent[1:]:
                    removeInfo = infoByPath[removePath]
                    reason = reasonToRemove(removePath, keepPath, removeInfo, keepInfo)
                    removeSize = int(removeInfo.get("size") or 0)
                    logger.value("remove", f"{removePath.name}  ({reason})")
                    toRemove.append((removePath, reason, removeSize))

            if not matchedComponentFound:
                logger.info(
                    "nothing to do – no matching duplicate set in group: %s",
                    displayNames,
                )
                skipped.append(displayNames)

    uniqueToRemove: Dict[Path, Tuple[str, int]] = {}
    for path, reason, size in toRemove:
        if path in uniqueToRemove:
            continue
        uniqueToRemove[path] = (reason, size)

    toRemove = [(path, reason, size) for path, (reason, size) in uniqueToRemove.items()]

    logger.done(
        f"summary: {len(toRemove)} to remove, {len(skipped)} skipped, {errors} error(s)"
    )

    if not toRemove:
        logSummaryBox("avi-mov", dryRun, 0, totalVideos, 0, logger)
        return

    logger.value("destination folder", str(dupesDir))
    moved = 0
    bytesPlanned = sum(size for _, _, size in toRemove)
    bytesMoved = 0
    for p, reason, size in toRemove:
        logger.action(f"move: {p}  ->  {dupesDir / p.name}  ({reason})")
        if confirm:
            try:
                safeMove(p, dupesDir)
                moved += 1
                bytesMoved += size
            except Exception as e:
                logger.error("Move failed for %s: %s", p.name, str(e))

    if confirm:
        logger.done(f"{moved} file(s) moved to {dupesDir}")
    else:
        logger.info("to actually move files, run with --confirm")

    deletedCount = moved if confirm else len(toRemove)
    bytesSaved = bytesMoved if confirm else bytesPlanned
    logSummaryBox("avi-mov", dryRun, deletedCount, totalVideos, bytesSaved, logger)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parseArgs():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Deduplicate video files. Defaults to same-name smart mode; "
            "use --sha256 for exact recursive deduplication."
        )
    )
    parser.add_argument(
        "--sha256",
        action="store_true",
        help=(
            "Use SHA-256 exact deduplication mode (recursive). "
            "Default mode is same-name smart comparison."
        ),
    )
    parser.add_argument(
        "--source",
        type=sourceDirPath,
        default=None,
        help=(
            "Source directory. Default is current directory in same-name mode, "
            "or /mnt/games1/Recovery/Videos with --sha256."
        ),
    )
    parser.add_argument(
        "--confirm",
        "-c",
        action="store_true",
        help="Actually move files.  Without this flag the script is a dry-run.",
    )

    return parser.parse_args()


def main() -> None:
    """Entry point: parse args, initialise logger, and dispatch to the chosen mode."""
    args = parseArgs()
    dryRun = not args.confirm
    mode = "sha256" if args.sha256 else "avi-mov"

    _name = Path(__file__).stem
    logger = getLogger(_name, includeConsole=True, dryRun=dryRun)

    if args.source is not None:
        sourceDir = Path(args.source)
    elif mode == "sha256":
        sourceDir = Path("/mnt/games1/Recovery/Videos")
    else:
        sourceDir = Path(".").resolve()

    logger.doing(_name)
    logger.value("source", str(sourceDir))
    logger.value("mode", mode)
    logger.value("dry run", str(dryRun))

    if mode == "sha256":
        runSha256(sourceDir, confirm=args.confirm, logger=logger)
    else:
        runAviMov(sourceDir, confirm=args.confirm, logger=logger)


if __name__ == "__main__":
    main()
