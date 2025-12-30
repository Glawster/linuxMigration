#!/usr/bin/env python3
"""
createKohyaDirs.py

Prepare/restore Kohya training folders using the logical structure:

  baseDataDir/
    styleName/
      train/
      output/
      originals/   (optional)

Key behaviours:
- Move/copy TOP-LEVEL images from style root into style/train
- As files are moved into train, rename to: "{style} #nn.ext"
- Captions follow the new filename: "{style} #nn.txt"
- If no caption exists, create one using captionTemplate
- Undo moves files from style/train back to style root but keeps renamed names

Config:
- automatically reads/writes ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Logging:
- prefix is "..." normally
- prefix is "...[] " when --dry-run is set
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Set

from kohyaUtils import (
    buildDefaultCaption,
    ensureDirs,
    getCaptionPath,
    isImageFile,
    resolveKohyaPaths,
    writeCaptionIfMissing,
)
from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateCfgFromArgs


def parseArgs() -> argparse.Namespace:
    cfg = loadConfig()

    defaultBaseDataDir = Path(getCfgValue(cfg, "baseDataDir", "/mnt/myVideo/Adult/tumblrForMovie"))
    defaultCaptionTemplate = getCfgValue(cfg, "captionTemplate", "{token}, photo")
    defaultCaptionExtension = getCfgValue(cfg, "captionExtension", ".txt")
    defaultCopyMode = bool(getCfgValue(cfg, "copyMode", False))
    defaultIncludeOriginalsDir = bool(getCfgValue(cfg, "includeOriginalsDir", False))

    parser = argparse.ArgumentParser(description="Create or restore Kohya training folder structure (style/train).")

    parser.add_argument(
        "--baseDataDir",
        type=Path,
        default=defaultBaseDataDir,
        help=f"root folder containing style folders (default: {defaultBaseDataDir})",
    )

    parser.add_argument(
        "--style",
        type=str,
        default=None,
        help="process only a specific style folder (e.g. 'kathy'). If omitted, processes all style folders.",
    )

    parser.add_argument(
        "--undo",
        action="store_true",
        help="restore from style/train back to a flat style folder structure (keeps renamed filenames)",
    )

    parser.add_argument(
        "--dry-run",
        dest="dryRun",
        action="store_true",
        help="show what would be done without changing anything",
    )

    parser.add_argument(
        "--captionTemplate",
        type=str,
        default=defaultCaptionTemplate,
        help=f"caption template used when creating missing captions (default: '{defaultCaptionTemplate}')",
    )

    parser.add_argument(
        "--captionExtension",
        type=str,
        default=defaultCaptionExtension,
        help=f"caption extension (default: {defaultCaptionExtension})",
    )

    parser.add_argument(
        "--includeOriginalsDir",
        action="store_true" if not defaultIncludeOriginalsDir else "store_false",
        help="toggle creation of style/originals directory (default from config)",
    )
    parser.set_defaults(includeOriginalsDir=defaultIncludeOriginalsDir)

    parser.add_argument(
        "--copy",
        action="store_true" if not defaultCopyMode else "store_false",
        help="toggle copy instead of move (default from config)",
    )
    parser.set_defaults(copy=defaultCopyMode)

    return parser.parse_args()


def updateConfigFromArgs(args: argparse.Namespace) -> bool:
    """Update configuration file with command-line arguments."""
    cfg = loadConfig()

    updates = {
        "baseDataDir": str(args.baseDataDir),
        "captionTemplate": args.captionTemplate,
        "captionExtension": args.captionExtension,
        "copyMode": bool(args.copy),
        "includeOriginalsDir": bool(args.includeOriginalsDir),
    }

    changed = updateCfgFromArgs(cfg, updates)
    if changed and not args.dryRun:
        saveConfig(cfg)

    return changed


def getStyleFolders(baseDataDir: Path, styleNameFilter: Optional[str]) -> List[Path]:
    if not baseDataDir.is_dir():
        raise FileNotFoundError(f"baseDataDir does not exist or is not a directory: {baseDataDir}")

    if styleNameFilter:
        styleDir = baseDataDir / styleNameFilter
        if not styleDir.is_dir():
            raise FileNotFoundError(f"style folder not found: {styleDir}")
        return [styleDir]

    return sorted([p for p in baseDataDir.iterdir() if p.is_dir()])


def listTopLevelImages(styleDir: Path) -> List[Path]:
    images: List[Path] = []
    for entry in styleDir.iterdir():
        if entry.is_dir():
            continue
        if isImageFile(entry):
            images.append(entry)
    return sorted(images)


def formatIndex(index: int) -> str:
    if index < 100:
        return f"{index:02d}"
    if index < 1000:
        return f"{index:03d}"
    return str(index)


def buildTargetStem(styleName: str, index: int) -> str:
    return f"{styleName} #{formatIndex(index)}"


def findUsedIndices(trainDir: Path, styleName: str) -> Set[int]:
    used: Set[int] = set()
    if not trainDir.exists():
        return used

    pattern = re.compile(rf"^{re.escape(styleName)}\s+#(\d+)$", re.IGNORECASE)

    for entry in trainDir.iterdir():
        if not entry.is_file():
            continue
        match = pattern.match(entry.stem)
        if match:
            try:
                used.add(int(match.group(1)))
            except ValueError:
                pass

    return used


def nextAvailableIndex(usedIndices: Set[int], startAt: int = 1) -> int:
    index = startAt
    while index in usedIndices:
        index += 1
    usedIndices.add(index)
    return index


def moveOrCopyFile(srcPath: Path, destPath: Path, copyMode: bool, dryRun: bool, prefix: str) -> None:
    print(f"{prefix}{'copy' if copyMode else 'move'}: {srcPath.name} -> {destPath}")
    if dryRun:
        return

    destPath.parent.mkdir(parents=True, exist_ok=True)

    if copyMode:
        import shutil
        shutil.copy2(srcPath, destPath)
    else:
        srcPath.rename(destPath)


def processStyleFolder(
    styleDir: Path,
    captionTemplate: str,
    captionExtension: str,
    dryRun: bool,
    includeOriginalsDir: bool,
    copyMode: bool,
    prefix: str,
) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, baseDataDir=styleDir.parent)

    ensureDirs(paths, includeOriginals=includeOriginalsDir)

    images = listTopLevelImages(styleDir)
    if not images:
        return

    defaultCaption = buildDefaultCaption(styleName=styleName, template=captionTemplate)
    usedIndices = findUsedIndices(paths.trainDir, styleName=styleName)

    for imagePath in images:
        index = nextAvailableIndex(usedIndices)
        targetStem = buildTargetStem(styleName, index)
        destImagePath = (paths.trainDir / targetStem).with_suffix(imagePath.suffix.lower())

        if destImagePath.exists():
            print(f"{prefix}skip: {destImagePath.name}")
            continue

        moveOrCopyFile(imagePath, destImagePath, copyMode=copyMode, dryRun=dryRun, prefix=prefix)

        srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
        destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

        if destCaptionPath.exists():
            continue

        if srcCaptionPath.exists():
            moveOrCopyFile(srcCaptionPath, destCaptionPath, copyMode=copyMode, dryRun=dryRun, prefix=prefix)
        else:
            # keep this silent unless it actually creates
            created = writeCaptionIfMissing(
                imagePath=destImagePath,
                captionText=defaultCaption,
                captionExtension=captionExtension,
                dryRun=dryRun,
            )
            if created:
                print(f"{prefix}caption: {destCaptionPath.name}")


def undoStyleFolder(styleDir: Path, dryRun: bool, copyMode: bool, prefix: str) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, baseDataDir=styleDir.parent)

    if not paths.trainDir.exists():
        return

    for entry in sorted(paths.trainDir.iterdir()):
        if not entry.is_file():
            continue

        destPath = styleDir / entry.name
        if destPath.exists():
            print(f"{prefix}skip: {destPath.name}")
            continue

        moveOrCopyFile(entry, destPath, copyMode=copyMode, dryRun=dryRun, prefix=prefix)

    if not dryRun and not copyMode:
        try:
            if paths.trainDir.exists() and not any(paths.trainDir.iterdir()):
                paths.trainDir.rmdir()
        except Exception:
            pass


def main() -> None:
    args = parseArgs()
    prefix = "...[] " if args.dryRun else "... "

    baseDataDir = args.baseDataDir.expanduser().resolve()

    try:
        styleFolders = getStyleFolders(baseDataDir, args.style)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    configChanged = updateConfigFromArgs(args)
    if configChanged and not args.dryRun:
        print(f"{prefix}updated config: {Path.home() / '.config/kohya/kohyaConfig.json'}")

    if args.undo:
        print(f"{prefix}undoing train structure in: {baseDataDir}")
        for styleDir in styleFolders:
            undoStyleFolder(styleDir=styleDir, dryRun=args.dryRun, copyMode=args.copy, prefix=prefix)
        return

    print(f"{prefix}scanning: {baseDataDir}")
    for styleDir in styleFolders:
        processStyleFolder(
            styleDir=styleDir,
            captionTemplate=args.captionTemplate,
            captionExtension=args.captionExtension,
            dryRun=args.dryRun,
            includeOriginalsDir=args.includeOriginalsDir,
            copyMode=args.copy,
            prefix=prefix,
        )


if __name__ == "__main__":
    main()
