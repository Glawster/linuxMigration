#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image
import imagehash


def main():
    parser = argparse.ArgumentParser(
        description="Perceptually deduplicate JPG images using pHash."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Images",
        help="Source directory containing images (default: /mnt/games1/Recovery/Images)",
    )
    parser.add_argument(
        "--dest",
        default="/mnt/games1/Recovery/Duplicates",
        help="Destination for duplicate images (default: /mnt/games1/Recovery/Duplicates)",
    )
    parser.add_argument(
        "--hashSize",
        type=int,
        default=16,
        help="Hash size for pHash (default: 16). Larger = slower but more precise.",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    dupeDir = Path(args.dest).expanduser().resolve()

    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    dupeDir.mkdir(parents=True, exist_ok=True)

    seen = {}
    moved = 0

    for f in srcDir.iterdir():
        if f.suffix.lower() not in [".jpg", ".jpeg"]:
            continue
        try:
            h = imagehash.phash(Image.open(f), hash_size=args.hashSize)
        except Exception:
            # Skip unreadable images silently; filterBlackImages.py should have caught most
            continue

        hStr = str(h)
        if hStr in seen:
            target = dupeDir / f.name
            i = 1
            while target.exists():
                target = dupeDir / f"{f.stem}_{i}{f.suffix}"
                i += 1
            f.rename(target)
            moved += 1
        else:
            seen[hStr] = f

    print(f"Moved {moved} duplicate images to {dupeDir}.")


if __name__ == "__main__":
    main()
