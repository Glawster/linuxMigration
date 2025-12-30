#!/usr/bin/env python3
"""
recoverOriginalsFromNames.py

For each file in a "wanted" folder, find a file with the same filename
somewhere under a source tree, and copy it to a destination folder.

Recommended usage for your workflow:
- wantedDir: /mnt/backup/kathy              (your current set)
- sourceRoot: /path/to/myPictures          (your big library)
- destDir: /mnt/backup/kathy/originals     (keeps originals separate)

By default this matches by filename only (case-insensitive).
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, List


imageExtensions = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def parseArgs() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy originals from a source tree by matching filenames.")

    parser.add_argument("--wantedDir", type=Path, required=True, help="folder containing files you want originals for")
    parser.add_argument("--sourceRoot", type=Path, required=True, help="root of your big photo library to search")
    parser.add_argument("--destDir", type=Path, required=True, help="where to copy found originals")

    parser.add_argument(
        "--extensions",
        type=str,
        default=",".join(sorted(imageExtensions)),
        help="comma-separated extensions to include (default: common image types)",
    )

    parser.add_argument(
        "--on-ambiguous",
        choices=["skip", "error", "pick-first"],
        default="error",
        help="what to do if multiple matches are found for a filename (default: error)",
    )

    parser.add_argument(
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="show what would happen without copying",
    )

    return parser.parse_args()


def listWantedFiles(wantedDir: Path, extensions: set[str]) -> List[Path]:
    wanted: List[Path] = []
    for p in sorted(wantedDir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() in extensions:
            wanted.append(p)
    return wanted


def buildSourceIndex(sourceRoot: Path, extensions: set[str]) -> Dict[str, List[Path]]:
    """
    Build a mapping: lowercase filename -> list of full paths under sourceRoot
    """
    index: Dict[str, List[Path]] = {}

    for p in sourceRoot.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in extensions:
            continue

        key = p.name.lower()
        index.setdefault(key, []).append(p)

    return index


def copyFile(srcPath: Path, destPath: Path, dryRun: bool) -> None:
    if dryRun:
        print(f"  [] would copy: {srcPath} -> {destPath}")
        return
    destPath.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(srcPath, destPath)


def run() -> None:
    args = parseArgs()
    prefix = "...[] " if args.dryRun else "..."

    wantedDir = args.wantedDir.expanduser().resolve()
    sourceRoot = args.sourceRoot.expanduser().resolve()
    destDir = args.destDir.expanduser().resolve()

    extensions = {e.strip().lower() for e in args.extensions.split(",") if e.strip()}
    if not extensions:
        sys.exit("ERROR: no extensions specified")

    print(f"{prefix}wanted dir: {wantedDir}")
    print(f"{prefix}source root: {sourceRoot}")
    print(f"{prefix}dest dir: {destDir}")
    print(f"{prefix}extensions: {', '.join(sorted(extensions))}")
    print(f"{prefix}on ambiguous: {args.on_ambiguous}")

    if not wantedDir.is_dir():
        sys.exit(f"ERROR: wantedDir not found: {wantedDir}")
    if not sourceRoot.is_dir():
        sys.exit(f"ERROR: sourceRoot not found: {sourceRoot}")

    wantedFiles = listWantedFiles(wantedDir, extensions)
    if not wantedFiles:
        sys.exit("ERROR: no wanted files found (check extensions)")

    print(f"{prefix}indexing source tree (this can take a while on large libraries)...")
    sourceIndex = buildSourceIndex(sourceRoot, extensions)
    print(f"{prefix}source index built: {len(sourceIndex)} unique filenames")

    copied = 0
    skipped = 0
    missing = 0
    ambiguous = 0

    for wantedPath in wantedFiles:
        key = wantedPath.name.lower()
        matches = sourceIndex.get(key, [])

        if not matches:
            print(f"WARNING: not found in source: {wantedPath.name}")
            missing += 1
            continue

        if len(matches) > 1:
            ambiguous += 1
            msg = f"WARNING: ambiguous ({len(matches)} matches): {wantedPath.name}"
            if args.on_ambiguous == "error":
                print(msg)
                for m in matches[:10]:
                    print(f"  - {m}")
                sys.exit("ERROR: ambiguous matches found (use --on-ambiguous skip|pick-first)")
            elif args.on_ambiguous == "skip":
                print(msg + " -> skipping")
                skipped += 1
                continue
            elif args.on_ambiguous == "pick-first":
                print(msg + f" -> picking first: {matches[0]}")
                srcPath = matches[0]
            else:
                # should never happen
                skipped += 1
                continue
        else:
            srcPath = matches[0]

        destPath = destDir / srcPath.name
        if destPath.exists():
            print(f"{prefix}skipping existing: {destPath.name}")
            skipped += 1
            continue

        print(f"{prefix}copying original for: {wantedPath.name}")
        copyFile(srcPath, destPath, dryRun=args.dryRun)
        copied += 1

    print(f"{prefix}done")
    print(f"{prefix}copied: {copied}, skipped: {skipped}, missing: {missing}, ambiguous: {ambiguous}")


if __name__ == "__main__":
    run()
