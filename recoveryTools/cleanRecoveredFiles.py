#!/usr/bin/env python3
"""
cleanRecoveredFiles.py

Scan PhotoRec recovery directories (recup_dir.*) from a source root,
validate and deduplicate files, and copy good ones to a target location.

- Images are validated with Pillow (PIL.Image.verify()).
- Images are also checked for "near-black" content (mean + stddev threshold).
- Invalid images (decode failure) and black images are counted separately.
- Videos are accepted based on extension + minimum size.
- Zero-byte / tiny files are skipped.
- Deduplication is done via SHA256 hash.
- Copies go into Images/, Videos/, Other/ under the target root.
- A cleanup_log.txt is written in the target describing what happened.

Default paths (can be overridden):

    source: /home/andy/Recovery
    target: /mnt/games1/Recovery
"""
import hashlib
import argparse
import shutil
import sys
import re
import time
from pathlib import Path
from typing import Dict, Set, Tuple

from PIL import Image, ImageStat, UnidentifiedImageError


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".mpg", ".mpeg", ".mts", ".m2ts", ".wmv"}


def isImage(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def isVideo(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS

def analyseImage(path: Path, blackMeanThresh: float, blackStdThresh: float) -> Tuple[bool, bool]:
    """
    Returns (isValid, isBlack)
    """
    try:
        with Image.open(path) as img:
            img.verify()
    except Exception:
        return False, False

    try:
        with Image.open(path).convert("RGB") as img2:
            stat = ImageStat.Stat(img2)
            mean = stat.mean
            stddev = stat.stddev
    except Exception:
        return False, False

    isBlack = all(m <= blackMeanThresh for m in mean) and \
              all(s <= blackStdThresh for s in stddev)

    return True, isBlack


def classifyFile(path: Path, minVideoSize: int) -> str:
    size = path.stat().st_size
    if size == 0:
        return "skip_tiny"

    if isImage(path):
        return "image"

    if isVideo(path):
        return "video" if size >= minVideoSize else "skip_tiny"

    return "other"


def ensureTargetSubdirs(targetRoot: Path):
    imgs = targetRoot / "Images"
    vids = targetRoot / "Videos"
    othr = targetRoot / "Other"
    imgs.mkdir(parents=True, exist_ok=True)
    vids.mkdir(parents=True, exist_ok=True)
    othr.mkdir(parents=True, exist_ok=True)
    return imgs, vids, othr

def seedExistingHashes(imgsDir: Path, vidsDir: Path, othDir: Path) -> Set[str]:
    """
    Pre-populate the hash set with any files that already exist
    in the target Images/Videos/Other folders. This lets us 'resume'
    across multiple runs without re-copying files we already wrote.
    """
    hashes: Set[str] = set()
    for d in (imgsDir, vidsDir, othDir):
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if not p.is_file():
                continue
            try:
                h = hashFile(p)
            except Exception:
                # If we can't hash an existing file, just skip it
                continue
            hashes.add(h)
    return hashes

def copyFile(src: Path, targetDir: Path, index: int) -> Path:
    name = f"{src.stem}_{index}{src.suffix.lower()}"
    out = targetDir / name
    while out.exists():
        index += 1
        out = targetDir / f"{src.stem}_{index}{src.suffix.lower()}"
    shutil.copy2(src, out)
    return out


def numericRecupDirs(sourceRoot: Path):
    dirs = [p for p in sourceRoot.iterdir() if p.is_dir() and p.name.startswith("recup_dir")]

    def key(p):
        m = re.search(r"(\d+)$", p.name)
        return int(m.group(1)) if m else 10**12

    return sorted(dirs, key=key)


def countTotalFiles(recupDirs) -> int:
    total = 0
    for d in recupDirs:
        for f in d.rglob("*"):
            if f.is_file():
                total += 1
    return total


def formatEta(seconds: float) -> str:
    if seconds <= 0 or seconds != seconds:  # NaN or negative
        return "--:--:--"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h > 99:
        return "99:59:59"
    return f"{h:02d}:{m:02d}:{s:02d}"

def hashFile(path: Path, chunkSize: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunkSize)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def printProgress(done: int, total: int, startTime: float, width: int = 40):
    if total == 0:
        return
    ratio = done / total
    if ratio > 1:
        ratio = 1
    filled = int(width * ratio)
    bar = "#" * filled + "-" * (width - filled)
    pct = int(ratio * 100)

    elapsed = time.time() - startTime
    if done > 0:
        perFile = elapsed / done
        remaining = (total - done) * perFile
    else:
        remaining = 0
    etaStr = formatEta(remaining)

    print(f"\rScanning: [{bar}] {pct:3d}% ({done}/{total}) ETA {etaStr}", end="", flush=True)


def processFiles(
    sourceRoot: Path,
    targetRoot: Path,
    minVideoSize: int,
    dryRun: bool,
    blackMean: float,
    blackStd: float,
    progressLog=None,
):

    imgsDir, vidsDir, othDir = ensureTargetSubdirs(targetRoot)
    hashesSeen: set[str] = set()

    stats = dict(
        totalFiles=0,
        imagesSeen=0,
        videosSeen=0,
        othersSeen=0,
        tinySkipped=0,
        imageInvalid=0,
        imageBlack=0,
        duplicatesSkipped=0,
        imagesCopied=0,
        videosCopied=0,
        othersCopied=0,
    )

    recupDirs = numericRecupDirs(sourceRoot)
    if not recupDirs:
        print("WARNING: no recup_dir.* folders found.")

    print("Counting files...")
    total = countTotalFiles(recupDirs)
    print(f"Total files: {total}")

    done = 0
    startTime = time.time()
    printProgress(done, total, startTime)

    index = 1

    for recup in recupDirs:
        for path in recup.rglob("*"):
            if not path.is_file():
                continue

            done += 1
            printProgress(done, total, startTime)

            if progressLog is not None:
                progressLog.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {path}\n")

            stats["totalFiles"] += 1
            kind = classifyFile(path, minVideoSize)

            if kind == "skip_tiny":
                stats["tinySkipped"] += 1
                continue

            if kind == "image":
                stats["imagesSeen"] += 1
                isValid, isBlack = analyseImage(path, blackMean, blackStd)
                if not isValid:
                    stats["imageInvalid"] += 1
                    continue
                if isBlack:
                    stats["imageBlack"] += 1
                    continue

            elif kind == "video":
                stats["videosSeen"] += 1
            else:
                stats["othersSeen"] += 1

            # Cheap resume/exists check:
            # if we've already copied *any* file derived from this PhotoRec file
            # (same stem, any index), skip it. This avoids re-copying on reruns
            # without needing to hash the entire target.
            if not dryRun:
                if kind == "image":
                    destDir = imgsDir
                elif kind == "video":
                    destDir = vidsDir
                else:
                    destDir = othDir

                pattern = f"{path.stem}_*{path.suffix.lower()}"
                if any(destDir.glob(pattern)):
                    stats["duplicatesSkipped"] += 1
                    continue

            # ---- SHA-256 dedupe (for both images & videos & other) ----
            try:
                fileHash = hashFile(path)
            except Exception:
                # If unreadable, treat as skipped but don't crash hashing
                stats["duplicatesSkipped"] += 1
                continue

            if fileHash in hashesSeen:
                stats["duplicatesSkipped"] += 1
                continue

            hashesSeen.add(fileHash)
            # -------------------------------------------------------------

            if dryRun:
                if kind == "image":
                    stats["imagesCopied"] += 1
                elif kind == "video":
                    stats["videosCopied"] += 1
                else:
                    stats["othersCopied"] += 1
                index += 1
                continue

            # the copy...
            if kind == "image":
                copyFile(path, imgsDir, index)
                stats["imagesCopied"] += 1
            elif kind == "video":
                copyFile(path, vidsDir, index)
                stats["videosCopied"] += 1
            else:
                copyFile(path, othDir, index)
                stats["othersCopied"] += 1

            index += 1

    printProgress(total, total, startTime)
    print()
    return stats


def writeLog(targetRoot: Path, stats: Dict[str, int]):
    log = targetRoot / "cleanup_log.txt"
    with log.open("w") as f:
        for k, v in stats.items():
            f.write(f"{k:20s}: {v}\n")
    print(f"Summary written to {log}")


def main():
    parser = argparse.ArgumentParser(description="Clean PhotoRec-recovered files.")
    parser.add_argument("--source", default="/home/andy/Recovery",
                        help="Source root containing recup_dir.*")
    parser.add_argument("--target", default="/mnt/games1/Recovery",
                        help="Target folder for cleaned files")
    parser.add_argument("--minVideoSize", type=int, default=10240,
                        help="Minimum video size (bytes)")
    parser.add_argument("--blackMean", type=float, default=2.0,
                        help="Brightness threshold for black detection")
    parser.add_argument("--blackStd", type=float, default=3.0,
                        help="Stddev threshold for black detection")
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan only; do not copy files")

    args = parser.parse_args()

    src = Path(args.source).resolve()
    tgt = Path(args.target).resolve()

    if not src.is_dir():
        sys.exit(f"ERROR: Source does not exist: {src}")

    tgt.mkdir(parents=True, exist_ok=True)

    # NEW: open a simple progress log you can tail -f
    progressLogPath = tgt / "cleanup_progress.log"
    progressLog = progressLogPath.open("a", encoding="utf-8", buffering=1)
    print(f"writing progress to {progressLogPath}")

    stats = processFiles(
        sourceRoot=src,
        targetRoot=tgt,
        minVideoSize=args.minVideoSize,
        dryRun=args.dry_run,
        blackMean=args.blackMean,
        blackStd=args.blackStd,
        progressLog=progressLog,
    )

    progressLog.close()

    print("\nDone.\n")
    for k, v in stats.items():
        print(f"{k:20s}: {v}")
    print()

    if not args.dry_run:
        writeLog(tgt, stats)


if __name__ == "__main__":
    main()
