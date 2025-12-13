#!/usr/bin/env python3
"""
filterBlackImages.py

Move near-black or invalid images out of the main Images folder
into BlackImages, with progress feedback and logging.
"""

import time
from pathlib import Path
from PIL import Image, ImageStat

from recoveryCommon import (
    isImage,
    printProgress,
    openStepLog,
)

# Thresholds (can later move to a config module)
BLACK_MEAN = 2.0
BLACK_STD = 3.0


def analyseImage(path: Path, blackMean: float, blackStd: float):
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

    isBlack = all(m <= blackMean for m in mean) and \
              all(s <= blackStd for s in stddev)

    return True, isBlack


def main():
    root = Path("/mnt/games1/Recovery")
    imagesDir = root / "Images"
    blackDir = root / "BlackImages"
    blackDir.mkdir(exist_ok=True)

    log = openStepLog(root, "filterBlackImages")

    # Collect image files
    images = [p for p in imagesDir.rglob("*") if p.is_file() and isImage(p)]
    total = len(images)

    print(f"Found {total} image files to check")

    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Filter black")

    moved = 0
    kept = 0

    for imgPath in images:
        done += 1
        printProgress(done, total, startTime, label="Filter black")

        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CHECK {imgPath}\n")

        isValid, isBlack = analyseImage(imgPath, BLACK_MEAN, BLACK_STD)

        if not isValid or isBlack:
            target = blackDir / imgPath.name
            counter = 1
            while target.exists():
                target = blackDir / f"{imgPath.stem}_{counter}{imgPath.suffix}"
                counter += 1

            imgPath.rename(target)
            moved += 1
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {imgPath} -> {target}\n")
        else:
            kept += 1

    print()  # finish progress line

    log.write(f"SUMMARY total={total} moved={moved} kept={kept}\n")
    log.close()

    print(f"filterBlackImages complete: total={total}, moved={moved}, kept={kept}")


if __name__ == "__main__":
    main()
