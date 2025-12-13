#!/usr/bin/env python3
import argparse
import time
from pathlib import Path
from PIL import Image

from recoveryCommon import isImage, printProgress, openStepLog


def iterCandidateFiles(srcDir: Path, recursive: bool):
    if recursive:
        for p in srcDir.rglob("*"):
            if p.is_file() and isImage(p):
                yield p
    else:
        for p in srcDir.iterdir():
            if p.is_file() and isImage(p):
                yield p


def main():
    parser = argparse.ArgumentParser(
        description="Sort images into folders by resolution (e.g. 1920x1080)."
    )
    parser.add_argument(
        "--source",
        default="/mnt/games1/Recovery/Images",
        help="Source directory containing images (default: /mnt/games1/Recovery/Images)",
    )
    parser.add_argument(
        "--target",
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
    targetRoot = Path(args.dest).expanduser().resolve()

    if not srcDir.is_dir():
        raise SystemExit(f"Source directory does not exist: {srcDir}")

    targetRoot.mkdir(parents=True, exist_ok=True)

    # log lives in Recovery root if possible, else in target root
    recoveryRoot = targetRoot.parent if targetRoot.parent.is_dir() else targetRoot
    log = openStepLog(recoveryRoot, "sortImagesByResolution")

    # two-pass: count then process (keeps memory low)
    total = sum(1 for _ in iterCandidateFiles(srcDir, args.recursive))
    print(f"Found {total} image files to sort")

    done = 0
    moved = 0
    skipped = 0
    errors = 0
    startTime = time.time()
    printProgress(done, total, startTime, label="Sort by resolution")

    for f in iterCandidateFiles(srcDir, args.recursive):
        done += 1
        printProgress(done, total, startTime, label="Sort by resolution")
        log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} CHECK {f}\n")

        try:
            with Image.open(f) as img:
                w, h = img.size
        except Exception as e:
            errors += 1
            log.write(f"ERROR {f}: {e}\n")
            continue

        folder = targetRoot / f"{w}x{h}"
        folder.mkdir(exist_ok=True)

        target = folder / f.name
        i = 1
        while target.exists():
            target = folder / f"{f.stem}_{i}{f.suffix}"
            i += 1

        try:
            f.rename(target)
            moved += 1
            log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} MOVE {f} -> {target}\n")
        except Exception as e:
            errors += 1
            log.write(f"ERROR {f} rename-> {target}: {e}\n")

    print()  # finish progress line

    # --- cleanup: remove empty resolution folders ---
    removedDirs = 0
    for d in sorted(targetRoot.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir():
            try:
                next(d.iterdir())
            except StopIteration:
                try:
                    d.rmdir()
                    removedDirs += 1
                    log.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} RMDIR {d}\n")
                except Exception as e:
                    log.write(f"ERROR rmdir {d}: {e}\n")

    log.write(
        f"SUMMARY total={total} moved={moved} removedDirs={removedDirs} errors={errors}\n"
    )
    log.close()

    print(
        f"Images sorted by resolution into {targetRoot}. "
        f"Moved {moved} files, removed {removedDirs} empty folders, errors {errors}."
    )

if __name__ == "__main__":
    main()