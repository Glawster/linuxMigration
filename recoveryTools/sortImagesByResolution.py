#!/usr/bin/env python3
import argparse
from pathlib import Path
from PIL import Image


def main():
    parser = argparse.ArgumentParser(
        description="Sort JPG images into folders by resolution (e.g. 1920x1080)."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Images",
        help="Source directory containing images (default: /mnt/games1/Recovery/Images)",
    )
    parser.add_argument(
        "--dest",
        default="/mnt/games1/Recovery/ImagesByResolution",
        help="Destination root for resolution folders (default: /mnt/games1/Recovery/ImagesByResolution)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan source directory (default: only top-level files).",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    dstRoot = Path(args.dest).expanduser().resolve()

    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    dstRoot.mkdir(parents=True, exist_ok=True)

    if args.recursive:
        files = srcDir.rglob("*.jpg")
    else:
        files = (p for p in srcDir.iterdir() if p.suffix.lower() in [".jpg", ".jpeg"])

    moved = 0
    for f in files:
        if f.suffix.lower() not in [".jpg", ".jpeg"]:
            continue
        try:
            with Image.open(f) as img:
                w, h = img.size
        except Exception:
            continue
        folder = dstRoot / f"{w}x{h}"
        folder.mkdir(exist_ok=True)
        target = folder / f.name
        i = 1
        while target.exists():
            target = folder / f"{f.stem}_{i}{f.suffix}"
            i += 1
        f.rename(target)
        moved += 1

    print(f"Images sorted by resolution into {dstRoot}. Moved {moved} files.")


if __name__ == "__main__":
    main()
