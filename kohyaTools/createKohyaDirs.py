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
- As files are moved into 10_styleName, rename to: "yyyymmdd-style-nn.ext"
  where yyyymmdd is the image date, nn is a sequence number
- Multiple files for the same date are handled with incrementing sequence numbers
- Captions follow the new filename: "yyyymmdd-style-nn.txt"
- If no caption exists, create one using captionTemplate
- Undo moves files from style/10_styleName back to style root but keeps renamed names

Config:
- automatically reads/writes ~/.config/kohya/kohyaConfig.json
- CLI overrides config for this run
- if CLI changes values, config is updated (unless --dry-run)

Logging:
- prefix is "..." normally
- prefix is "...[]" when --dry-run is set
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path
from typing import List, Optional, Set, Tuple

from kohyaUtils import (
    buildDefaultCaption,
    ensureDirs,
    getCaptionPath,
    getImageDate,
    isImageFile,
    resolveKohyaPaths,
    sortImagesByDate,
    updateExifDate,
    writeCaptionIfMissing,
    stripPNGMetadata
)
from kohyaConfig import loadConfig, saveConfig, getCfgValue, updateConfigFromArgs


# Constants for date formatting
FALLBACK_DATE_STRING = "00000000"  # Used when no date is available
DATE_FORMAT_LENGTH = 8  # YYYYMMDD format


def parseArgs() -> argparse.Namespace:
    """
    Parse command-line arguments with defaults loaded from config.
    
    Returns:
        Parsed command-line arguments
    """
    cfg = loadConfig()

    defaultTrainingRoot = Path(getCfgValue(cfg, "trainingRoot", "/mnt/myVideo/Adult/tumblrForMovie"))
    defaultCaptionTemplate = getCfgValue(cfg, "captionTemplate", "{token}, photo")
    defaultCaptionExtension = getCfgValue(cfg, "captionExtension", ".txt")
    defaultIncludeOriginalsDir = bool(getCfgValue(cfg, "includeOriginalsDir", False))

    parser = argparse.ArgumentParser(description="Create or restore Kohya training folder structure (style/train).")

    parser.add_argument(
        "--trainingRoot",
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
            "that don't match the expected 'yyyymmdd-style-nn.ext' naming"
        ),
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

    return parser.parse_args()


def getStyleFolders(trainingRoot: Path, styleNameFilter: Optional[str]) -> List[Path]:
    """
    Get list of style folders to process.
    
    Args:
        trainingRoot: Base directory containing style folders
        styleNameFilter: Optional specific style name to process
        
    Returns:
        List of style folder paths
        
    Raises:
        FileNotFoundError: If trainingRoot or specific style folder doesn't exist
    """
    if not trainingRoot.is_dir():
        raise FileNotFoundError(f"trainingRoot does not exist or is not a directory: {trainingRoot}")

    if styleNameFilter:
        styleDir = trainingRoot / styleNameFilter
        if not styleDir.is_dir():
            raise FileNotFoundError(f"style folder not found: {styleDir}")
        return [styleDir]

    return sorted([p for p in trainingRoot.iterdir() if p.is_dir()])


def formatIndex(index: int) -> str:
    """
    Format an index number with zero-padding to a minimum of 2 digits.
    
    Args:
        index: Index number to format
        
    Returns:
        Zero-padded string with minimum 2 digits (e.g., "01", "02", "99", "123")
        
    Examples:
        formatIndex(1) -> "01"
        formatIndex(99) -> "99"
        formatIndex(123) -> "123"
    """
    return f"{index:02d}"


def listTopLevelImages(styleDir: Path) -> List[Path]:
    """
    List all image files directly in the style directory (not in subdirectories).
    
    Args:
        styleDir: Style directory to scan
        
    Returns:
        Sorted list of image file paths at the top level of the directory
        
    Note:
        Excludes images in subdirectories like 10_styleName, output, originals
    """
    if not styleDir.exists() or not styleDir.is_dir():
        return []
    
    images = []
    for entry in styleDir.iterdir():
        if entry.is_file() and isImageFile(entry):
            images.append(entry)
    
    return sorted(images)



def checkAndFixStyleFolder(
    styleDir: Path,
    captionExtension: str,
    dryRun: bool,
    prefix: str,
) -> None:
    """Validate and fix filenames inside style/10_styleName."""
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, trainingRoot=styleDir.parent)

    if not paths.trainDir.exists():
        print(f"{prefix} check: missing train dir, skipping: {paths.trainDir}")
        return

    # Build list of images currently in trainDir
    images = [p for p in sorted(paths.trainDir.iterdir()) if isImageFile(p)]
    if not images:
        return

    # Sort by best-available date to keep renames stable
    imagesWithDates = sortImagesByDate(images, updateExif=False, prefix=prefix)

    # Cache used indices per date. Start with indices already present in correctly named files.
    usedIndicesCache: dict[str, Set[int]] = {}
    for img in images:
        stripPNGMetadata(imagePath=img, dryRun=dryRun, prefix=prefix)
        if isCorrectKohyaStem(img.stem, styleName=styleName):
            dateStr = img.stem[:DATE_FORMAT_LENGTH]
            if dateStr not in usedIndicesCache:
                usedIndicesCache[dateStr] = set()
            idx = parseKohyaStemIndex(img.stem, styleName=styleName)
            if idx is not None:
                usedIndicesCache[dateStr].add(idx)

    # Track captions so we can also flag orphans
    captions = {p.name: p for p in paths.trainDir.iterdir() if p.is_file() and p.suffix == captionExtension}

    renamedImages = 0
    renamedCaptions = 0

    for imagePath, imageDate in imagesWithDates:
        dateStr = imageDate.strftime("%Y%m%d")

        # Ensure cache exists
        if dateStr not in usedIndicesCache:
            usedIndicesCache[dateStr] = findUsedIndices(paths.trainDir, styleName=styleName, dateStr=dateStr)
        usedIndices = usedIndicesCache[dateStr]

        # If already correct (and index already reserved), leave it.
        if isCorrectKohyaStem(imagePath.stem, styleName=styleName) and imagePath.stem.startswith(dateStr):
            continue

        index = nextAvailableIndex(usedIndices)
        targetStem = buildTargetStem(styleName=styleName, index=index, dateStr=dateStr)
        destImagePath = (paths.trainDir / targetStem).with_suffix(imagePath.suffix.lower())

        # Caption move/rename alongside image
        srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
        destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

        if renameFileSafe(imagePath, destImagePath, dryRun=dryRun, prefix=prefix):
            renamedImages += 1
            # If we renamed the image, update imagePath reference for caption logic
            imagePath = destImagePath

        # Rename caption if it exists and destination doesn't
        if srcCaptionPath.exists() and not destCaptionPath.exists():
            if renameFileSafe(srcCaptionPath, destCaptionPath, dryRun=dryRun, prefix=prefix):
                renamedCaptions += 1

    # Report orphan captions
    if captions:
        imageStems = {p.stem for p in paths.trainDir.iterdir() if isImageFile(p)}
        orphans = []
        for capName, capPath in captions.items():
            if capPath.stem not in imageStems:
                orphans.append(capName)
        if orphans:
            print(f"{prefix} check: orphan captions in {paths.trainDir.name}: {len(orphans)} (e.g. {orphans[0]})")

    if renamedImages or renamedCaptions:
        print(f"{prefix} check: renamed images: {renamedImages}, captions: {renamedCaptions} in {styleName}")



def isCorrectKohyaStem(stem: str, styleName: str) -> bool:
    """Return True if stem matches 'yyyymmdd-styleName-nn' for this style."""
    pattern = re.compile(
        rf"^\d{{{DATE_FORMAT_LENGTH}}}-{re.escape(styleName)}-(\d+)$",
        re.IGNORECASE,
    )
    return bool(pattern.match(stem))


def parseKohyaStemIndex(stem: str, styleName: str) -> Optional[int]:
    """Parse the index from a correctly-named kohya stem, else None."""
    pattern = re.compile(
        rf"^\d{{{DATE_FORMAT_LENGTH}}}-{re.escape(styleName)}-(\d+)$",
        re.IGNORECASE,
    )
    match = pattern.match(stem)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def renameFileSafe(srcPath: Path, destPath: Path, dryRun: bool, prefix: str) -> bool:
    """Rename srcPath to destPath, guarding against collisions. Returns True if renamed."""
    if srcPath == destPath:
        return False

    if destPath.exists():
        print(f"ERROR: destination exists, cannot rename: {srcPath.name} -> {destPath.name}")
        return False

    print(f"{prefix} rename: {srcPath.name} -> {destPath.name}")
    if dryRun:
        return True

    destPath.parent.mkdir(parents=True, exist_ok=True)
    srcPath.rename(destPath)
    return True


def buildTargetStem(styleName: str, index: int, dateStr: str = "") -> str:
    """
    Build a target filename stem in the format 'yyyymmdd-styleName-nn'.
    
    Args:
        styleName: Style/person name
        index: Index number
        dateStr: Date string in YYYYMMDD format (e.g., "20040117")
        
    Returns:
        Formatted filename stem
    """
    if dateStr:
        return f"{dateStr}-{styleName}-{formatIndex(index)}"
    else:
        # Fallback if no date available
        return f"{FALLBACK_DATE_STRING}-{styleName}-{formatIndex(index)}"


def findUsedIndices(trainDir: Path, styleName: str, dateStr: str = "") -> Set[int]:
    """
    Find all index numbers already used in trainDir for the given style and date.
    
    Args:
        trainDir: Training directory to scan
        styleName: Style name to match in filenames
        dateStr: Date string in YYYYMMDD format (optional)
        
    Returns:
        Set of index numbers already in use
    """
    used: Set[int] = set()
    if not trainDir.exists():
        return used

    # New format: yyyymmdd-styleName-nn
    # Also support old format for backward compatibility: styleName #nn
    if dateStr:
        pattern = re.compile(rf"^{re.escape(dateStr)}-{re.escape(styleName)}-(\d+)$", re.IGNORECASE)
    else:
        # Match any date with this style name
        pattern = re.compile(rf"^\d{{{DATE_FORMAT_LENGTH}}}-{re.escape(styleName)}-(\d+)$", re.IGNORECASE)
    
    # Also check old format for backward compatibility
    old_pattern = re.compile(rf"^{re.escape(styleName)}\s+#(\d+)$", re.IGNORECASE)

    for entry in trainDir.iterdir():
        if not entry.is_file():
            continue
        # Try new format first
        match = pattern.match(entry.stem)
        if not match:
            # Try old format
            match = old_pattern.match(entry.stem)
        
        if match:
            try:
                used.add(int(match.group(1)))
            except ValueError:
                pass

    return used


def nextAvailableIndex(usedIndices: Set[int], startAt: int = 1) -> int:
    """
    Find the next available index number not in the used set.
    
    Args:
        usedIndices: Set of already-used indices (will be updated)
        startAt: Starting index number
        
    Returns:
        Next available index number
    """
    index = startAt
    while index in usedIndices:
        index += 1
    usedIndices.add(index)
    return index


def moveFile(srcPath: Path, destPath: Path, dryRun: bool, prefix: str) -> None:
    """
    Move a file from source to destination.
    
    Args:
        srcPath: Source file path
        destPath: Destination file path
        dryRun: If True, only print action without executing
        prefix: Logging prefix string
        
    Raises:
        OSError: If move operation fails
    """
    print(f"{prefix} move: {srcPath.name} -> {destPath}")
    if dryRun:
        return

    destPath.parent.mkdir(parents=True, exist_ok=True)
    srcPath.rename(destPath)


def processStyleFolder(
    styleDir: Path,
    captionTemplate: str,
    captionExtension: str,
    dryRun: bool,
    includeOriginalsDir: bool,
    prefix: str,
) -> None:
    """
    Process a style folder: move images to train dir and create captions.
    
    Args:
        styleDir: Style folder to process
        captionTemplate: Template for default captions
        captionExtension: Caption file extension
        dryRun: If True, only print actions without executing
        includeOriginalsDir: Whether to create originals directory
        prefix: Logging prefix string
    """
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, trainingRoot=styleDir.parent)

    ensureDirs(paths, includeOriginals=includeOriginalsDir)

    images = listTopLevelImages(styleDir)
    if not images:
        return

    # Sort images by date (EXIF, filename pattern, or modification time)
    # Always update EXIF data from filename dates when possible
    # Returns list of (imagePath, date) tuples sorted by date
    imagesWithDates = sortImagesByDate(images, updateExif=(not dryRun), prefix=prefix)

    defaultCaption = buildDefaultCaption(styleName=styleName, template=captionTemplate)

    # Cache used indices per date to avoid redundant filesystem scans
    usedIndicesCache = {}

    for imagePath, imageDate in imagesWithDates:
        # Format date as YYYYMMDD for filename
        dateStr = imageDate.strftime("%Y%m%d")
        
        # Get or compute used indices for this date
        if dateStr not in usedIndicesCache:
            usedIndicesCache[dateStr] = findUsedIndices(paths.trainDir, styleName=styleName, dateStr=dateStr)
        usedIndices = usedIndicesCache[dateStr]
        
        index = nextAvailableIndex(usedIndices)
        targetStem = buildTargetStem(styleName, index, dateStr)
        destImagePath = (paths.trainDir / targetStem).with_suffix(imagePath.suffix.lower())

        if destImagePath.exists():
            print(f"{prefix} skip: {destImagePath.name}")
            continue

        try:
            moveFile(imagePath, destImagePath, dryRun=dryRun, prefix=prefix)
        except OSError as e:
            print(f"ERROR: failed to move {imagePath.name}: {e}")
            continue

        srcCaptionPath = getCaptionPath(imagePath, captionExtension=captionExtension)
        destCaptionPath = getCaptionPath(destImagePath, captionExtension=captionExtension)

        if destCaptionPath.exists():
            continue

        if srcCaptionPath.exists():
            try:
                moveFile(srcCaptionPath, destCaptionPath, dryRun=dryRun, prefix=prefix)
            except OSError as e:
                print(f"ERROR: failed to move caption {srcCaptionPath.name}: {e}")
        else:
            # keep this silent unless it actually creates
            created = writeCaptionIfMissing(
                imagePath=destImagePath,
                captionText=defaultCaption,
                captionExtension=captionExtension,
                dryRun=dryRun,
            )
            if created:
                print(f"{prefix} caption: {destCaptionPath.name}")


def undoStyleFolder(styleDir: Path, dryRun: bool, prefix: str) -> None:
    """
    Undo train structure: move files from train dir back to style root.
    
    Args:
        styleDir: Style folder to process
        dryRun: If True, only print actions without executing
        prefix: Logging prefix string
    """
    styleName = styleDir.name
    paths = resolveKohyaPaths(styleName=styleName, trainingRoot=styleDir.parent)

    if not paths.trainDir.exists():
        return

    for entry in sorted(paths.trainDir.iterdir()):
        if not entry.is_file():
            continue

        destPath = styleDir / entry.name
        if destPath.exists():
            print(f"{prefix} skip: {destPath.name}")
            continue

        try:
            moveFile(entry, destPath, dryRun=dryRun, prefix=prefix)
        except OSError as e:
            print(f"ERROR: failed to move {entry.name}: {e}")
            continue

    if not dryRun:
        try:
            if paths.trainDir.exists() and not any(paths.trainDir.iterdir()):
                paths.trainDir.rmdir()
        except Exception:
            pass


def main() -> None:
    """
    Main entry point: parse arguments, validate setup, and process style folders.
    
    Raises:
        SystemExit: On validation failures or errors during processing
    """
    args = parseArgs()
    prefix = "...[]" if args.dryRun else "..."

    # Check if PIL is available for EXIF extraction
    try:
        from PIL import Image
        pil_available = True
    except ImportError:
        pil_available = False
        print(f"{prefix} WARNING: PIL/Pillow not installed - EXIF dates will not be extracted")
        print(f"{prefix}          Install with: pip install pillow")

    trainingRoot = args.trainingRoot.expanduser().resolve()

    try:
        styleFolders = getStyleFolders(trainingRoot, args.style)
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    cfg = loadConfig()
    updates = {
        "trainingRoot": str(args.trainingRoot),
        "captionTemplate": args.captionTemplate,
        "captionExtension": args.captionExtension,
        "includeOriginalsDir": bool(args.includeOriginalsDir),
    }
    configChanged = updateConfigFromArgs(cfg, updates=updates)
    if configChanged and not args.dryRun:
        saveConfig(cfg)
        print(f"{prefix} updated config: {Path.home() / '.config/kohya/kohyaConfig.json'}")

    if args.undo:
        print(f"{prefix} undoing train structure in: {trainingRoot}")
        for styleDir in styleFolders:
            undoStyleFolder(styleDir=styleDir, dryRun=args.dryRun, prefix=prefix)
        return

    if args.check:
        print(f"{prefix} checking existing kohya structure in: {trainingRoot}")
        for styleDir in styleFolders:
            checkAndFixStyleFolder(
                styleDir=styleDir,
                captionExtension=args.captionExtension,
                dryRun=args.dryRun,
                prefix=prefix,
            )
        return

    print(f"{prefix} scanning: {trainingRoot}")
    if pil_available:
        print(f"{prefix} EXIF extraction enabled (PIL available)")
    
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
