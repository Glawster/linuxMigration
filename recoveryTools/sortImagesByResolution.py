#!/usr/bin/env python3
""" 
sortImagesByResolution.py

Sort images into folders by resolution, grouped into width buckets.

Output layout:
  <target>/w_<LOW>-<HIGH>/<filename>

Example:
  ImagesByResolution/w_0400-0599/foo.jpg

At the end, empty resolution folders and empty bucket folders are removed.
"""

import argparse
import time
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image

from recoveryCommon import isImage, printProgress, openStepLog


def iterCandidateFiles(srcDir: Path, recursive: bool):
    if recursive:
        for p in srcDir.rglob("*"):
            if p.is_file() and isImage(p):
                yield p
    else:
        for p in srcDir.iterdir():
            if p.is_file() and isImage(p):
                yield p


def buildWidthBins(widths: List[int], binSize: int) -> List[Tuple[int, int]]:
    """Build inclusive bins [low, high] covering widths."""
    if not widths:
        return []

    maxW = max(widths)
    # start at 0 so thumbnails fall into sensible early buckets
    bins: List[Tuple[int, int]] = []
    low = 0
    while low <= maxW:
        high = low + (binSize - 1)
        bins.append((low, high))
        low = high + 1
    return bins


def findBin(width: int, bins: List[Tuple[int, int]]) -> Tuple[int, int]:
    for low, high in bins:
        if low <= width <= high:
            return low, high
    # Fallback (should not happen if bins cover max width)
    return bins[-1]


def binLabel(low: int, high: int) -> str:
    return f"w_{low:04d}-{high:04d}"


def safeRename(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    target = dst
    i = 1
    while target.exists():
        target = dst.with_name(f"{dst.stem}_{i}{dst.suffix}")
        i += 1
    src.rename(target)
    return target


def removeEmptyDirs(root: Path, log) -> int:
    """Remove empty directories under root, bottom-up."""
    removed = 0
    for d in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if not d.is_dir():
            continue
        try:
            next(d.iterdir())
        except StopIteration:
            try:
                d.rmdir()
                removed += 1
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} RMDIR {d}")
            except Exception as e:
                log.write(f"ERROR rmdir {d}: {e}")
    return removed


def main():
    parser = argparse.ArgumentParser(
        description="Sort images into folders by resolution, grouped by width buckets."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Images",
        help="Source directory containing images (default: /mnt/games1/Recovery/Images)",
    )
    parser.add_argument(
        "--target",
        default="/mnt/games1/Recovery/ImagesByResolution",
        help="Destination root (default: /mnt/games1/Recovery/ImagesByResolution)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan source directory (default: only top-level files).",
    )
    parser.add_argument(
        "--width-bin",
        type=int,
        default=200,
        help="Width bucket size (default: 200). Examples: 200 gives <200, 200-399, 400-599...",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    targetRoot = Path(args.target).expanduser().resolve()

    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    targetRoot.mkdir(parents=True, exist_ok=True)

    recoveryRoot = targetRoot.parent if targetRoot.parent.is_dir() else targetRoot
    log = openStepLog(recoveryRoot, "sortImagesByResolution")

    # ---- Pass 1: read sizes, build bins ----
    files = list(iterCandidateFiles(srcDir, args.recursive))
    total = len(files)
    print(f"Found {total} image files to sort")

    widths: List[int] = []
    sizes: Dict[Path, Tuple[int, int]] = {}

    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Reading sizes")

    errors = 0
    for f in files:
        done += 1
        printProgress(done, total, startTime, label="Reading sizes")
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} SIZE {f}")

        try:
            with Image.open(f) as img:
                w, h = img.size
            sizes[f] = (w, h)
            widths.append(w)
        except Exception as e:
            errors += 1
            log.write(f"ERROR {f} size: {e}")

    print()  # end sizes progress line

    bins = buildWidthBins(widths, args.width_bin)
    if not bins:
        log.write("SUMMARY total=0 moved=0 removedDirs=0 errors=0")
        log.close()
        print("No images found.")
        return

    log.write(
        f"{time.strftime('%Y-%m-%d %H:%M:%S')} BINS width_bin={args.width_bin} bins={bins}"
    )

    # ---- Pass 2: move files into bucket folders ----
    moved = 0
    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Sorting")

    for f in files:
        done += 1
        printProgress(done, total, startTime, label="Sorting")

        if f not in sizes:
            # size-read failed
            continue

        w, h = sizes[f]
        low, high = findBin(w, bins)

        bucketDir = targetRoot / binLabel(low, high)

        try:
            dst = safeRename(f, bucketDir / f.name)
            moved += 1
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {f} -> {dst}")
        except Exception as e:
            errors += 1
            log.write(f"ERROR {f} rename: {e}")

    print()  # finish sorting progress line

    # ---- Cleanup empty dirs (bucket only) ----
    removedDirs = removeEmptyDirs(targetRoot, log)

    log.write(
        f"SUMMARY total={total} moved={moved} removedDirs={removedDirs} errors={errors} widthBin={args.width_bin}"
    )
    log.close()

    print(
        f"Images sorted into {targetRoot}. "
        f"Moved {moved} files, removed {removedDirs} empty folders, errors {errors}."
    )


if __name__ == "__main__":
    main()
