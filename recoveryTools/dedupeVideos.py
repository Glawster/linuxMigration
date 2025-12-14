#!/usr/bin/env python3
"""
dedupeVideos.py

Exact deduplication of video files using SHA-256.

- Operates directly on an existing Videos folder (no flattening / copying)
- Keeps the first-seen copy in place
- Moves duplicates into a VideoDuplicates folder *inside the source folder*
- Always scans recursively
- Writes a tail-able log file into the source folder

Designed to be run AFTER recovery/flattening.
"""

import argparse
import hashlib
import time
from pathlib import Path
from typing import Dict

from recoveryCommon import isVideo, printProgress, openStepLog


def hashFile(path: Path, chunkSize: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunkSize)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def safeMove(src: Path, dstDir: Path) -> Path:
    dstDir.mkdir(parents=True, exist_ok=True)
    target = dstDir / src.name
    i = 1
    while target.exists():
        target = dstDir / f"{src.stem}_{i}{src.suffix}"
        i += 1
    src.rename(target)
    return target


def main():
    parser = argparse.ArgumentParser(
        description="Deduplicate video files in-place using SHA-256."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Videos",
        help="Source folder containing videos (default: /mnt/games1/Recovery/Videos)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not move files; only report what would be moved",
    )
    args = parser.parse_args()

    srcDir = Path(args.source).expanduser().resolve()
    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    # Log and duplicates folder live INSIDE the source folder
    log = openStepLog(srcDir, "dedupeVideos")
    dupesDir = srcDir / "VideoDuplicates"

    # Always recursive
    videos = [p for p in srcDir.rglob("*") if p.is_file() and isVideo(p)]
    total = len(videos)
    print(f"Found {total} video files to dedupe")

    done = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Dedupe videos")

    seen: Dict[str, Path] = {}

    kept = 0
    moved = 0
    errors = 0

    for v in videos:
        done += 1
        printProgress(done, total, startTime, label="Dedupe videos")
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CHECK {v}\n")

        try:
            h = hashFile(v)
        except Exception as e:
            errors += 1
            log.write(f"ERROR {v} hash: {e}\n")
            continue

        if h not in seen:
            seen[h] = v
            kept += 1
            continue

        # duplicate
        if args.dry_run:
            moved += 1
            log.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} WOULD_MOVE {v} (dup of {seen[h]})\n"
            )
            continue

        try:
            dst = safeMove(v, dupesDir)
            moved += 1
            log.write(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {v} -> {dst} (dup of {seen[h]})\n"
            )
        except Exception as e:
            errors += 1
            log.write(f"ERROR {v} move: {e}\n")

    print()
    log.write(
        f"SUMMARY total={total} kept={kept} moved={moved} errors={errors} dryRun={args.dry_run}\n"
    )
    log.close()

    print(
        f"dedupeVideos complete: total={total}, kept={kept}, moved={moved}, errors={errors}"
    )


if __name__ == "__main__":
    main()
