#!/usr/bin/env python3
"""
createKohyaDirs.py

Prepare/restore Kohya training folders using the logical structure:

  trainingRoot/
    styleName/
      10_styleName/
      output/
      originals/   (optional)

Key behaviours:
- Move TOP-LEVEL images from style root into style/10_styleName
- As files are moved into 10_styleName, rename to: "style-nn.ext"
  where nn is a sequence number (01, 02, ...)
- Captions follow the new filename: "style-nn.txt" (or chosen extension)
- If no caption exists, create one using captionTemplate
- Undo moves files from style/10_styleName back to style root but keeps renamed filenames

Config:
- automatically reads/writes ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Logging:
- prefix is "..."
- prefix is "...[]" when --dry-run is set
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
    stripPNGMetadata,
    writeCaptionIfMissing,
    setLogger as setLoggerUtils
)
from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateConfigFromArgs, setLogger as setLoggerConfig
from organiseMyProjects.logUtils import getLogger  # type: ignore

def parseArgs() -> argparse.Namespace:
    cfg = loadConfig()

    defaultTrainingRoot = Path(getCfgValue(cfg, "trainingRoot", "/mnt/myVideo/Adult/tumblrForMovie"))
    defaultCaptionTemplate = getCfgValue(cfg, "captionTemplate", "{token}, photo")
    defaultCaptionExtension = getCfgValue(cfg, "captionExtension", ".txt")
    defaultIncludeOriginalsDir = bool(getCfgValue(cfg, "includeOriginalsDir", False))

    parser = argparse.ArgumentParser(description="Create or restore Kohya training folder structure (style/train).")

    parser.add_argument(
        "--training",
        type=Path,
        default=defaultTrainingRoot,
        help=f"root folder containing style folders (default: {defaultTrainingRoot})",
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
        "--check",
        action="store_true",
        help=(
            "check existing kohya structure (10_style folders) and rename files/captions "
            "that don't match the expected 'style-nn.ext' naming"
        ),
    )

    parser.add_argument(
        "--confirm",
        action="store_true",
        help="execute changes (default is dry-run mode)",
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

    return parser.parse_args()


def getStyleFolders(trainingRoot: Path, styleNameFilter: Optional[str]) -> List[Path]:
    if not trainingRoot.is_dir():
        raise FileNotFoundError(f"trainingRoot does not exist or is not a directory: {trainingRoot}")

    if styleNameFilter:
        styleDir = trainingRoot / styleNameFilter
        if not styleDir.is_dir():
            raise FileNotFoundError(f"style folder not found: {styleDir}")
        return [styleDir]

    return sorted([p for p in trainingRoot.iterdir() if p.is_dir()])


def formatIndex(index: int) -> str:
    return f"{index:02d}"


def listTopLevelImages(styleDir: Path) -> List[Path]:
    if not styleDir.exists() or not styleDir.is_dir():
        return []

    images: List[Path] = []
    for entry in styleDir.iterdir():
        if entry.is_file() and isImageFile(entry):
            images.append(entry)
    return sorted(images)


def isCorrectKohyaStem(stem: str, styleName: str) -> bool:
    pattern = re.compile(rf"^{re.escape(styleName)}-(\d+)$", re.IGNORECASE)
    return bool(pattern.match(stem))


def renameFileSafe(srcPath: Path, destPath: Path, dryRun: bool, prefix: str) -> bool:
    if srcPath == destPath:
        return False

    if destPath.exists():
        logger.error(f"ERROR: Destination exists, cannot rename: {srcPath.name} -> {destPath.name}")
        return False

    logger.info(f"{prefix} rename: {srcPath.name} -> {destPath.name}")
    if dryRun:
        return True

    destPath.parent.mkdir(parents=True, exist_ok=True)
    srcPath.rename(destPath)
    return True


def buildTargetStem(styleName: str, index: int) -> str:
    return f"{styleName}-{formatIndex(index)}"


def findUsedIndices(trainDir: Path, styleName: str) -> Set[int]:
    used: Set[int] = set()
    if not trainDir.exists():
        return used

    pattern = re.compile(rf"^{re.escape(styleName)}-(\d+)$", re.IGNORECASE)

    # Backward compatibility:
    old_date_pattern = re.compile(rf"^\d{{8}}-{re.escape(styleName)}-(\d+)$", re.IGNORECASE)
    old_hash_pattern = re.compile(rf"^{re.escape(styleName)}\s+#(\d+)$", re.IGNORECASE)

    for entry in trainDir.iterdir():
        if not entry.is_file():
            continue

        match = pattern.match(entry.stem) or old_date_pattern.match(entry.stem) or old_hash_pattern.match(entry.stem)
        if not match:
            continue

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


def moveFile(srcPath: Path, destPath: Path, dryRun: bool, prefix: str) -> None:
    logger.info(f"{prefix} move: {srcPath.name} -> {destPath}")
    if dryRun:
        return

    destPath.parent.mkdir(parents=True, exist_ok=True)
    srcPath.rename(destPath)


def checkAndFixStyleFolder(styleDir: Path, captionExtension: str, captionTemplate: str, dryRun: bool, prefix: str) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, trainingRoot=styleDir.parent)

    if not paths.trainDir.exists():
        logger.info(f"{prefix} check: missing train dir, skipping: {paths.trainDir}")
        return

    images = [p for p in sorted(paths.trainDir.iterdir()) if isImageFile(p)]
    if not images:
        return

    usedIndices = findUsedIndices(paths.trainDir, styleName=styleName)
    captions = {p.name: p for p in paths.trainDir.iterdir() if p.is_file() and p.suffix == captionExtension}

    renamedImages = 0
    renamedCaptions = 0
    imageMapping = {}  # Track original -> renamed paths for caption creation

    for imagePath in images:
        stripPNGMetadata(imagePath=imagePath, dryRun=dryRun, prefix=prefix)

        finalImagePath = imagePath  # Track final path (renamed or original)
        
        if not isCorrectKohyaStem(imagePath.stem, styleName=styleName):
            index = nextAvailableIndex(usedIndices)
            targetStem = buildTargetStem(styleName=styleName, index=index)
            destImagePath = (paths.trainDir / targetStem).with_suffix(imagePath.suffix.lower())

            srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
            destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

            if renameFileSafe(imagePath, destImagePath, dryRun=dryRun, prefix=prefix):
                renamedImages += 1
                finalImagePath = destImagePath  # Update to new path

            if srcCaptionPath.exists() and not destCaptionPath.exists():
                if renameFileSafe(srcCaptionPath, destCaptionPath, dryRun=dryRun, prefix=prefix):
                    renamedCaptions += 1
        
        imageMapping[imagePath] = finalImagePath

    # Create missing caption files for images without captions
    defaultCaption = buildDefaultCaption(styleName=styleName, template=captionTemplate)
    createdCaptions = 0
    
    for finalPath in imageMapping.values():
        created = writeCaptionIfMissing(
            imagePath=finalPath,
            captionText=defaultCaption,
            captionExtension=captionExtension,
            dryRun=dryRun,
        )
        if created:
            createdCaptions += 1
            captionPath = getCaptionPath(finalPath, captionExtension=captionExtension)
            logger.info(f"{prefix} added caption: {captionPath.name}")

    if captions:
        imageStems = {p.stem for p in paths.trainDir.iterdir() if isImageFile(p)}
        orphans = []
        for capName, capPath in captions.items():
            if capPath.stem not in imageStems:
                orphans.append(capName)
        if orphans:
            logger.info(f"{prefix} found orphan captions in {paths.trainDir.name}: {len(orphans)} (e.g. {orphans[0]})")

    if renamedImages or renamedCaptions or createdCaptions:
        logger.info(f"{prefix} renamed images: {renamedImages}, captions: {renamedCaptions}, created captions: {createdCaptions} in {styleName}")


def processStyleFolder(
    styleDir: Path,
    captionTemplate: str,
    captionExtension: str,
    dryRun: bool,
    includeOriginalsDir: bool,
    prefix: str,
) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, trainingRoot=styleDir.parent)

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
            logger.info(f"{prefix} skip: {destImagePath.name}")
            continue

        try:
            moveFile(imagePath, destImagePath, dryRun=dryRun, prefix=prefix)
        except OSError as e:
            logger.error(f"ERROR: Failed to move {imagePath.name}: {e}")
            continue

        srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
        destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

        if destCaptionPath.exists():
            continue

        if srcCaptionPath.exists():
            try:
                moveFile(srcCaptionPath, destCaptionPath, dryRun=dryRun, prefix=prefix)
            except OSError as e:
                logger.error(f"ERROR: Failed to move caption {srcCaptionPath.name}: {e}")
        else:
            created = writeCaptionIfMissing(
                imagePath=destImagePath,
                captionText=defaultCaption,
                captionExtension=captionExtension,
                dryRun=dryRun,
            )
            if created:
                logger.info(f"{prefix} caption: {destCaptionPath.name}")


def undoStyleFolder(styleDir: Path, dryRun: bool, prefix: str) -> None:
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, trainingRoot=styleDir.parent)

    if not paths.trainDir.exists():
        return

    for entry in sorted(paths.trainDir.iterdir()):
        if not entry.is_file():
            continue

        destPath = styleDir / entry.name
        if destPath.exists():
            logger.info(f"{prefix} skip: {destPath.name}")
            continue

        try:
            moveFile(entry, destPath, dryRun=dryRun, prefix=prefix)
        except OSError as e:
            logger.error(f"ERROR: Failed to move {entry.name}: {e}")
            continue

    if not dryRun:
        try:
            if paths.trainDir.exists() and not any(paths.trainDir.iterdir()):
                paths.trainDir.rmdir()
        except Exception:
            pass


def main() -> None:
    args = parseArgs()
    args.dryRun = not args.confirm
    prefix = "...[]" if args.dryRun else "..."

    global logger
    logger = getLogger("createKohyaDirs", includeConsole=True)
    setLoggerUtils(logger)
    setLoggerConfig(logger)

    trainingRoot = args.training.expanduser().resolve()

    try:
        styleFolders = getStyleFolders(trainingRoot, args.style)
    except Exception as e:
        logger.error(f"ERROR: {e}")
        sys.exit(1)

    cfg = loadConfig()
    updates = {
        "trainingRoot": str(args.training),
        "captionTemplate": args.captionTemplate,
        "captionExtension": args.captionExtension,
        "includeOriginalsDir": bool(args.includeOriginalsDir),
    }
    configChanged = updateConfigFromArgs(cfg, updates=updates)

    if configChanged and not args.dryRun:
        saveConfig(cfg)

    if configChanged:
        logger.info(f"{prefix} updated config: {Path.home() / '.config/kohya/kohyaConfig.json'}")

    if args.undo:
        logger.info(f"{prefix} undoing train structure in: {trainingRoot}")
        for styleDir in styleFolders:
            undoStyleFolder(styleDir=styleDir, dryRun=args.dryRun, prefix=prefix)
        return

    if args.check:
        logger.info(f"{prefix} checking existing kohya structure in: {trainingRoot}")
        for styleDir in styleFolders:
            checkAndFixStyleFolder(styleDir, args.captionExtension, args.captionTemplate, args.dryRun, prefix)
        return

    logger.info(f"{prefix} scanning: {trainingRoot}")

    for styleDir in styleFolders:
        processStyleFolder(
            styleDir=styleDir,
            captionTemplate=args.captionTemplate,
            captionExtension=args.captionExtension,
            dryRun=args.dryRun,
            includeOriginalsDir=args.includeOriginalsDir,
            prefix=prefix,
        )


if __name__ == "__main__":
    main()
