#!/usr/bin/env python3
import argparse
import csv
import datetime
import time
from pathlib import Path
from typing import Optional

from PIL import Image, ExifTags

from recoveryCommon import isImage, printProgress, openStepLog


TAG_DATETIME_ORIGINAL = None
for k, v in ExifTags.TAGS.items():
    if v == "DateTimeOriginal":
        TAG_DATETIME_ORIGINAL = k
        break


def getDateTime(path: Path) -> datetime.datetime:
    # Favour EXIF DateTimeOriginal, fall back to file mtime
    try:
        with Image.open(path) as img:
            exif = img._getexif() or {}
            if TAG_DATETIME_ORIGINAL in exif:
                dtStr = exif[TAG_DATETIME_ORIGINAL]
                # "YYYY:MM:DD HH:MM:SS" -> "YYYY-MM-DD HH:MM:SS"
                dtStr = dtStr.replace(":", "-", 2)
                return datetime.datetime.fromisoformat(dtStr)
    except Exception:
        pass
    return datetime.datetime.fromtimestamp(path.stat().st_mtime)


def iterImages(rootDir: Path):
    for f in rootDir.rglob("*"):
        if f.is_file() and isImage(f):
            yield f


def main():
    parser = argparse.ArgumentParser(
        description="Build a chronological CSV timeline from images (EXIF DateTimeOriginal or file mtime)."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/ImagesByResolution",
        help="Root directory of images (default: /mnt/games1/Recovery/ImagesByResolution)",
    )
    parser.add_argument(
        "--output",
        default="/mnt/games1/Recovery/image_timeline.csv",
        help="Output CSV path (default: /mnt/games1/Recovery/image_timeline.csv)",
    )
    args = parser.parse_args()

    rootDir = Path(args.source).expanduser().resolve()
    outCsv = Path(args.output).expanduser().resolve()

    if not rootDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {rootDir}")

    recoveryRoot = outCsv.parent
    log = openStepLog(recoveryRoot, "buildImageTimeline")

    # two-pass count for progress
    total = sum(1 for _ in iterImages(rootDir))
    print(f"Found {total} image files to index")

    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Timeline")

    rows = []
    errors = 0

    for f in iterImages(rootDir):
        done += 1
        printProgress(done, total, startTime, label="Timeline")
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CHECK {f}\n")

        dt = getDateTime(f)

        try:
            with Image.open(f) as img:
                w, h = img.size
        except Exception as e:
            w = h = None
            errors += 1
            log.write(f"ERROR {f} size: {e}\n")

        rows.append((dt, w, h, str(f)))

    rows.sort(key=lambda r: r[0])
    outCsv.parent.mkdir(parents=True, exist_ok=True)

    with outCsv.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["datetime", "width", "height", "path"])
        for dt, w, h, p in rows:
            writer.writerow([dt.isoformat(" "), w, h, p])

    print()  # finish progress line
    log.write(f"SUMMARY total={total} rows={len(rows)} errors={errors} output={outCsv}\n")
    log.close()

    print(f"Timeline written to {outCsv} (rows: {len(rows)}; errors: {errors}).")


if __name__ == "__main__":
    main()
