#!/usr/bin/env python3
"""
recoverOriginalsFromNames.py

For each file in wantedDir, find a file with the same filename somewhere under
sourceRoot, then copy it to destDir.

Config:
- automatically reads/writes ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Logging:
- prefix is "..." normally
- prefix is "...[] " when --dry-run is set

Notes:
- This matches by filename only (case-insensitive).
- If multiple matches are found, default behaviour is to error.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Set

from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateCfgFromArgs


defaultExtensions = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}


def parseArgs() -> argparse.Namespace:
    cfg = loadConfig()

    defaultPicturesRoot = Path(getCfgValue(cfg, "picturesRoot", "/mnt/myPictures/Pictures"))
    defaultBackupRoot = Path(getCfgValue(cfg, "backupRoot", "/mnt/backup"))
    defaultWantedDir = Path(getCfgValue(cfg, "wantedDir", str(defaultBackupRoot / "kathy")))
    defaultDestDir = Path(getCfgValue(cfg, "originalsDestDir", str(defaultBackupRoot / "kathy" / "originals")))
    defaultSourceRoot = Path(getCfgValue(cfg, "sourceRoot", str(defaultPicturesRoot)))

    defaultExts = getCfgValue(cfg, "extensions", ",".join(sorted(defaultExtensions)))
    defaultOnAmbiguous = getCfgValue(cfg, "onAmbiguous", "error")

    parser = argparse.ArgumentParser(description="Copy originals from a source tree by matching filenames.")

    parser.add_argument("--wantedDir", type=Path, default=defaultWantedDir, help=f"wanted folder (default: {defaultWantedDir})")
    parser.add_argument("--sourceRoot", type=Path, default=defaultSourceRoot, help=f"source tree root (default: {defaultSourceRoot})")
    parser.add_argument("--destDir", type=Path, default=defaultDestDir, help=f"destination folder (default: {defaultDestDir})")

    parser.add_argument(
        "--extensions",
        type=str,
        default=defaultExts,
        help="comma-separated extensions to include",
    )

    parser.add_argument(
        "--on-ambiguous",
        choices=["skip", "error", "pick-first"],
        default=defaultOnAmbiguous,
        dest="onAmbiguous",
        help="what to do if multiple matches are found",
    )

    parser.add_argument(
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="show actions without executing",
    )

    return parser.parse_args()


def updateConfigFromArgs(args: argparse.Namespace) -> bool:
    cfg = loadConfig()

    updates = {
        "picturesRoot": str(Path(getCfgValue(cfg, "picturesRoot", "/mnt/myPictures/Pictures"))),
        "backupRoot": str(Path(getCfgValue(cfg, "backupRoot", "/mnt/backup"))),
        "wantedDir": str(args.wantedDir),
        "sourceRoot": str(args.sourceRoot),
        "originalsDestDir": str(args.destDir),
        "extensions": args.extensions,
        "onAmbiguous": args.onAmbiguous,
    }

    changed = updateCfgFromArgs(cfg, updates)
    if changed and not args.dryRun:
        saveConfig(cfg)

    return changed


def parseExtensions(extString: str) -> Set[str]:
    exts = {e.strip().lower() for e in extString.split(",") if e.strip()}
    return exts


def listWantedFiles(wantedDir: Path, extensions: Set[str]) -> List[Path]:
    wanted: List[Path] = []
    for p in sorted(wantedDir.iterdir()):
        if not p.is_file():
            continue
        if p.suffix.lower() in extensions:
            wanted.append(p)
    return wanted


def buildSourceIndex(sourceRoot: Path, extensions: Set[str]) -> Dict[str, List[Path]]:
    index: Dict[str, List[Path]] = {}

    for p in sourceRoot.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() not in extensions:
            continue

        index.setdefault(p.name.lower(), []).append(p)

    return index


def copyFile(srcPath: Path, destDir: Path, dryRun: bool, prefix: str) -> None:
    destPath = destDir / srcPath.name

    if destPath.exists():
        print(f"{prefix} skip: {destPath.name}")
        return

    print(f"{prefix} copy: {srcPath.name} -> {destPath}")
    if dryRun:
        return

    destDir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(srcPath, destPath)


def main() -> None:
    args = parseArgs()
    prefix = "...[] " if args.dryRun else "..."

    wantedDir = args.wantedDir.expanduser().resolve()
    sourceRoot = args.sourceRoot.expanduser().resolve()
    destDir = args.destDir.expanduser().resolve()

    if not wantedDir.is_dir():
        sys.exit(f"ERROR: wantedDir not found: {wantedDir}")
    if not sourceRoot.is_dir():
        sys.exit(f"ERROR: sourceRoot not found: {sourceRoot}")

    configChanged = updateConfigFromArgs(args)
    if configChanged and not args.dryRun:
        print(f"{prefix} updated config: {Path.home() / '.config/kohya/kohyaConfig.json'}")

    extensions = parseExtensions(args.extensions)

    wantedFiles = listWantedFiles(wantedDir, extensions)
    if not wantedFiles:
        sys.exit("ERROR: no wanted files found (check extensions)")

    print(f"{prefix} indexing: {sourceRoot}")
    sourceIndex = buildSourceIndex(sourceRoot, extensions)

    for wantedPath in wantedFiles:
        matches = sourceIndex.get(wantedPath.name.lower(), [])

        if not matches:
            print(f"{prefix} missing: {wantedPath.name}")
            continue

        if len(matches) > 1:
            if args.onAmbiguous == "skip":
                print(f"{prefix} ambiguous: {wantedPath.name}")
                continue
            if args.onAmbiguous == "pick-first":
                print(f"{prefix} ambiguous: {wantedPath.name}")
                copyFile(matches[0], destDir, args.dryRun, prefix)
                continue

            # error
            print(f"ERROR: ambiguous matches for: {wantedPath.name}")
            for m in matches[:10]:
                print(f"  - {m}")
            sys.exit(1)

        copyFile(matches[0], destDir, args.dryRun, prefix)


if __name__ == "__main__":
    main()
