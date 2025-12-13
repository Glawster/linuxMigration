#!/usr/bin/env python3
"""
dedupeImages.py

Perceptual deduplication of images using pHash.
Keeps one copy of visually-identical images in the source directory.
Moves duplicates into Duplicates/ subfolder, preserving directory structure.
"""

import argparse
import time
from pathlib import Path
from PIL import Image
import imagehash

from recoveryCommon import (
    isImage,
    printProgress,
    openStepLog,
)

# pHash distance threshold
# 0 = identical hash, higher = more tolerant
PHASH_THRESHOLD = 0


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate images in place using perceptual hashing."
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Source directory to scan for images",
    )
    args = parser.parse_args()

    sourceDir = Path(args.source).expanduser().resolve()
    
    if not sourceDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {sourceDir}")

    dupesDir = sourceDir / "Duplicates"
    dupesDir.mkdir(exist_ok=True)

    log = openStepLog(sourceDir, "dedupeImages")

    # Collect image files
    images = [p for p in sourceDir.rglob("*") if p.is_file() and isImage(p) and not p.is_relative_to(dupesDir)]
    total = len(images)

    print(f"Found {total} image files to dedupe")

    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Dedupe images")

    # Map pHash -> kept image path
    seen = {}

    kept = 0
    moved = 0
    errors = 0

    for imgPath in images:
        done += 1
        printProgress(done, total, startTime, label="Dedupe images")

        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CHECK {imgPath}\n")

        try:
            with Image.open(imgPath) as img:
                phash = imagehash.phash(img)
        except Exception as e:
            errors += 1
            log.write(f"ERROR {imgPath}: {e}\n")
            continue

        matched = None
        for existingHash, existingPath in seen.items():
            if phash - existingHash <= PHASH_THRESHOLD:
                matched = existingPath
                break

        if matched is None:
            seen[phash] = imgPath
            kept += 1
        else:
            # Preserve directory structure relative to source
            relPath = imgPath.relative_to(sourceDir)
            target = dupesDir / relPath
            target.parent.mkdir(parents=True, exist_ok=True)
            
            counter = 1
            while target.exists():
                target = target.parent / f"{imgPath.stem}_{counter}{imgPath.suffix}"
                counter += 1

            imgPath.rename(target)
            moved += 1
            log.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {imgPath} -> {target} (dup of {matched})\n"
            )

    print()  # finish progress line

    log.write(
        f"SUMMARY total={total} kept={kept} moved={moved} errors={errors}\n"
    )
    log.close()

    print(
        f"dedupeImages complete: total={total}, kept={kept}, moved={moved}, errors={errors}"
    )


if __name__ == "__main__":
    main()
