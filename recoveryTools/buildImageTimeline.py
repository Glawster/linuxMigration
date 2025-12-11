#!/usr/bin/env python3
import argparse
import csv
import datetime
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ExifTags

TAG_DATETIME_ORIGINAL = None
for k, v in ExifTags.TAGS.items():
    if v == "DateTimeOriginal":
        TAG_DATETIME_ORIGINAL = k
        break


def getDateTime(path: Path) -> datetime.datetime:
    # Favour EXIF DateTimeOriginal, fall back to file mtime
    try:
        img = Image.open(path)
        exif = img._getexif() or {}
        if TAG_DATETIME_ORIGINAL in exif:
            dtStr = exif[TAG_DATETIME_ORIGINAL]
            dtStr = dtStr.replace(":", "-", 2)
            return datetime.datetime.fromisoformat(dtStr)
    except Exception:
        pass
    return datetime.datetime.fromtimestamp(path.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(
        description="Build a chronological CSV timeline from images."
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
    parser.add_argument(
        "--ext",
        default=".jpg",
        help="Image extension to scan for (default: .jpg)",
    )
    args = parser.parse_args()

    rootDir = Path(args.source).expanduser().resolve()
    outCsv = Path(args.output).expanduser().resolve()

    if not rootDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {rootDir}")

    rows = []
    for f in rootDir.rglob(f"*{args.ext}"):
        dt = getDateTime(f)
        try:
            with Image.open(f) as img:
                w, h = img.size
        except Exception:
            w = h = None
        rows.append((dt, w, h, str(f)))

    rows.sort(key=lambda r: r[0])
    outCsv.parent.mkdir(parents=True, exist_ok=True)

    with outCsv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["datetime", "width", "height", "path"])
        for dt, w, h, p in rows:
            writer.writerow([dt.isoformat(" "), w, h, p])

    print(f"Timeline written to {outCsv} (rows: {len(rows)}).")


if __name__ == "__main__":
    main()
