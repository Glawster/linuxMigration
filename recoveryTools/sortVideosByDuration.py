#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path


def getDurationSeconds(path: Path):
    try:
        cmd = [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_entries",
            "format=duration",
            str(path),
        ]
        out = subprocess.check_output(cmd)
        data = json.loads(out)
        dur = float(data["format"]["duration"])
        return int(round(dur))
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Sort MP4 videos into folders by duration (seconds)."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Videos",
        help="Source directory containing videos (default: /mnt/games1/Recovery/Videos)",
    )
    parser.add_argument(
        "--dest",
        default="/mnt/games1/Recovery/VideosByDuration",
        help="Destination root for duration buckets (default: /mnt/games1/Recovery/VideosByDuration)",
    )
    parser.add_argument(
        "--ext",
        default=".mp4",
        help="Video extension to scan for (default: .mp4)",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    dstRoot = Path(args.dest).expanduser().resolve()

    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    dstRoot.mkdir(parents=True, exist_ok=True)

    moved = 0
    for f in srcDir.iterdir():
        if f.suffix.lower() != args.ext.lower():
            continue
        dur = getDurationSeconds(f)
        folder = dstRoot / ("corrupt" if dur is None else f"{dur}_sec")
        folder.mkdir(exist_ok=True)
        target = folder / f.name
        i = 1
        while target.exists():
            target = folder / f"{f.stem}_{i}{f.suffix}"
            i += 1
        f.rename(target)
        moved += 1

    print(f"Videos sorted by duration into {dstRoot}. Moved {moved} files.")


if __name__ == "__main__":
    main()
