#!/usr/bin/env python3
import argparse
import json
import subprocess
import time
from pathlib import Path

from recoveryCommon import isVideo, printProgress, openStepLog


def getDurationSeconds(path: Path):
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_entries", "format=duration",
            str(path),
        ]
        out = subprocess.check_output(cmd)
        data = json.loads(out)
        dur = float(data["format"]["duration"])
        return int(round(dur))
    except Exception:
        return None


def iterVideos(srcDir: Path, recursive: bool):
    if recursive:
        for p in srcDir.rglob("*"):
            if p.is_file() and isVideo(p):
                yield p
    else:
        for p in srcDir.iterdir():
            if p.is_file() and isVideo(p):
                yield p


def main():
    parser = argparse.ArgumentParser(
        description="Sort videos into folders by duration (seconds) using ffprobe."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Videos",
        help="Source directory containing videos (default: /mnt/games1/Recovery/Videos)",
    )
    parser.add_argument(
        "--target",
        default="/mnt/games1/Recovery/VideosByDuration",
        help="Destination root for duration buckets (default: /mnt/games1/Recovery/VideosByDuration)",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Recursively scan source directory (default: only top-level files).",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    targetRoot = Path(args.target).expanduser().resolve()
    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    targetRoot.mkdir(parents=True, exist_ok=True)
    recoveryRoot = targetRoot.parent if targetRoot.parent.is_dir() else targetRoot
    log = openStepLog(recoveryRoot, "sortVideosByDuration")

    total = sum(1 for _ in iterVideos(srcDir, args.recursive))
    print(f"Found {total} video files to sort")

    done = 0
    moved = 0
    corrupt = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Sort videos")

    for f in iterVideos(srcDir, args.recursive):
        done += 1
        printProgress(done, total, startTime, label="Sort videos")
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CHECK {f}\n")

        dur = getDurationSeconds(f)
        folder = targetRoot / ("corrupt" if dur is None else f"{dur}_sec")
        folder.mkdir(exist_ok=True)

        target = folder / f.name
        i = 1
        while target.exists():
            target = folder / f"{f.stem}_{i}{f.suffix}"
            i += 1

        try:
            f.rename(target)
            moved += 1
            if dur is None:
                corrupt += 1
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {f} -> {target} dur=None\n")
            else:
                log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {f} -> {target} dur={dur}\n")
        except Exception as e:
            log.write(f"ERROR {f} rename-> {target}: {e}\n")

    print()  # finish progress line
    log.write(f"SUMMARY total={total} moved={moved} corrupt={corrupt} target={targetRoot}\n")
    log.close()

    print(f"Videos sorted by duration into {targetRoot}. Moved {moved} files. Corrupt {corrupt}.")

if __name__ == "__main__":
    main()
