#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image, ImageStat, UnidentifiedImageError


def looksBlack(path: Path, meanThresh: float = 2.0, stdThresh: float = 3.0) -> bool:
    try:
        img = Image.open(path).convert("RGB")
        stat = ImageStat.Stat(img)
        mean = stat.mean
        std = stat.stddev
    except Exception:
        # If we can't read it properly, treat as bad/black
        return True

    if all(m <= meanThresh for m in mean) and all(s <= stdThresh for s in std):
        return True
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Move near-black JPG images from source to dest."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Images",
        help="Source directory containing images (default: /mnt/games1/Recovery/Images)",
    )
    parser.add_argument(
        "--dest",
        default="/mnt/games1/Recovery/BlackImages",
        help="Destination for black/empty images (default: /mnt/games1/Recovery/BlackImages)",
    )
    parser.add_argument(
        "--meanThresh",
        type=float,
        default=2.0,
        help="Mean brightness threshold for black detection (default: 2.0)",
    )
    parser.add_argument(
        "--stdThresh",
        type=float,
        default=3.0,
        help="Stddev threshold for black detection (default: 3.0)",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    badDir = Path(args.dest).expanduser().resolve()

    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    badDir.mkdir(parents=True, exist_ok=True)

    moved = 0
    for f in srcDir.iterdir():
        if f.suffix.lower() not in [".jpg", ".jpeg"]:
            continue
        if looksBlack(f, meanThresh=args.meanThresh, stdThresh=args.stdThresh):
            target = badDir / f.name
            i = 1
            while target.exists():
                target = badDir / f"{f.stem}_{i}{f.suffix}"
                i += 1
            f.rename(target)
            moved += 1

    print(f"Moved {moved} black/corrupt images from {srcDir} to {badDir}.")


if __name__ == "__main__":
    main()
