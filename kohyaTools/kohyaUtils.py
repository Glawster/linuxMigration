#!/usr/bin/env python3
"""
kohyaUtils.py

Shared helpers for kohya dataset preparation + training.

Folder layout standard:
  baseDataDir/
    styleName/
      train/
      output/
      originals/   (optional)

CamelCase naming to match your project standards.
"""

from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".cr2", ".nef"}


@dataclass(frozen=True)
class KohyaPaths:
    styleName: str
    baseDataDir: Path
    styleDir: Path
    trainDir: Path
    outputDir: Path
    originalsDir: Path


def resolveKohyaPaths(styleName: str, baseDataDir: Path) -> KohyaPaths:
    """
    Resolve all standard kohya paths for a given style.
    
    Args:
        styleName: Name of the style/person
        baseDataDir: Base directory containing style folders
        
    Returns:
        KohyaPaths object with all resolved paths
        
    Raises:
        ValueError: If styleName is empty or contains invalid characters
    """
    if not styleName or not str(styleName).strip():
        raise ValueError("styleName cannot be empty")
    
    styleDir = baseDataDir / styleName
    trainDir = styleDir / "train"
    outputDir = styleDir / "output"
    originalsDir = styleDir / "originals"
    return KohyaPaths(
        styleName=styleName,
        baseDataDir=baseDataDir,
        styleDir=styleDir,
        trainDir=trainDir,
        outputDir=outputDir,
        originalsDir=originalsDir,
    )


def ensureDirs(paths: KohyaPaths, includeOriginals: bool = False) -> None:
    """
    Create all required directories for a kohya training setup.
    
    Args:
        paths: KohyaPaths object with directory paths
        includeOriginals: Whether to also create the originals directory
    """
    paths.styleDir.mkdir(parents=True, exist_ok=True)
    paths.trainDir.mkdir(parents=True, exist_ok=True)
    paths.outputDir.mkdir(parents=True, exist_ok=True)
    if includeOriginals:
        paths.originalsDir.mkdir(parents=True, exist_ok=True)


def isImageFile(filePath: Path) -> bool:
    """Check if a file is a supported image type."""
    return filePath.is_file() and filePath.suffix.lower() in IMAGE_EXTENSIONS


def listImageFiles(folderPath: Path, recursive: bool = False) -> List[Path]:
    """
    List all image files in a folder.
    
    Args:
        folderPath: Directory to search
        recursive: Whether to search subdirectories
        
    Returns:
        Sorted list of image file paths
    """
    if not folderPath.exists():
        return []

    if recursive:
        candidates = folderPath.rglob("*")
    else:
        candidates = folderPath.glob("*")

    return sorted([p for p in candidates if isImageFile(p)])


def getCaptionPath(imagePath: Path, captionExtension: str = ".txt") -> Path:
    """
    Get the caption file path for an image.
    
    For "photo.jpg" returns "photo.txt".
    """
    return imagePath.with_suffix(captionExtension)


def captionExists(imagePath: Path, captionExtension: str = ".txt") -> bool:
    """Check if a caption file exists for the given image."""
    return getCaptionPath(imagePath, captionExtension).exists()


def buildDefaultCaption(styleName: str, template: str = "{token}, photo") -> str:
    """
    Build a default caption from a template.
    
    Identity-friendly default caption template supports {token} placeholder.
    """
    return template.format(token=styleName).strip()


def writeCaptionIfMissing(
    imagePath: Path,
    captionText: str,
    captionExtension: str = ".txt",
    dryRun: bool = False,
) -> bool:
    """
    Write caption file if it doesn't exist.
    
    Args:
        imagePath: Path to the image file
        captionText: Caption text to write
        captionExtension: Caption file extension
        dryRun: If True, simulate action without writing
        
    Returns:
        True if a caption was created, False if it already existed
    """
    captionPath = getCaptionPath(imagePath, captionExtension)

    if captionPath.exists():
        return False

    if dryRun:
        return True

    captionPath.write_text(captionText + "\n", encoding="utf-8")
    return True


def ensureCaptionsForFolder(
    trainDir: Path,
    styleName: str,
    captionExtension: str = ".txt",
    captionTemplate: str = "{token}, photo",
    recursive: bool = False,
    dryRun: bool = False,
) -> Tuple[int, int]:
    """
    Ensure captions exist for all images in trainDir.
    
    Args:
        trainDir: Directory containing training images
        styleName: Name of the style/person
        captionExtension: Caption file extension
        captionTemplate: Template for default captions
        recursive: Whether to search recursively
        dryRun: If True, simulate actions without writing
        
    Returns:
        Tuple of (total_images, captions_created)
    """
    images = listImageFiles(trainDir, recursive=recursive)
    captionText = buildDefaultCaption(styleName, template=captionTemplate)

    createdCount = 0
    for imagePath in images:
        if writeCaptionIfMissing(
            imagePath=imagePath,
            captionText=captionText,
            captionExtension=captionExtension,
            dryRun=dryRun,
        ):
            createdCount += 1

    return (len(images), createdCount)


def validateTrainingSet(
    trainDir: Path,
    minImages: int = 10,
    captionExtension: str = ".txt",
    requireCaptions: bool = True,
    recursive: bool = False,
) -> List[str]:
    """
    Validate a training dataset directory.
    
    Args:
        trainDir: Directory containing training data
        minImages: Minimum required number of images
        captionExtension: Caption file extension
        requireCaptions: Whether captions are required for all images
        recursive: Whether to search recursively
        
    Returns:
        List of human-readable problem descriptions (empty if valid)
        
    Note:
        Does not perform face detection; only checks structure and file counts
    """
    problems: List[str] = []

    images = listImageFiles(trainDir, recursive=recursive)
    if len(images) < minImages:
        problems.append(f"not enough images: found {len(images)}, need at least {minImages}")

    if requireCaptions:
        missing = []
        for imagePath in images:
            if not captionExists(imagePath, captionExtension=captionExtension):
                missing.append(imagePath.name)
        if missing:
            problems.append(f"missing captions for {len(missing)} images (e.g. {missing[0]})")

    return problems


def moveFiles(
    sourceFiles: Sequence[Path],
    destDir: Path,
    dryRun: bool = False,
) -> int:
    """
    Move multiple files into a destination directory.
    
    Args:
        sourceFiles: Sequence of source file paths
        destDir: Destination directory
        dryRun: If True, simulate actions without moving
        
    Returns:
        Number of files moved (or would be moved in dry run)
    """
    destDir.mkdir(parents=True, exist_ok=True)
    moved = 0

    for src in sourceFiles:
        if not src.exists():
            continue

        destPath = destDir / src.name
        if dryRun:
            moved += 1
            continue

        src.rename(destPath)
        moved += 1

    return moved


def copyFiles(
    sourceFiles: Sequence[Path],
    destDir: Path,
    dryRun: bool = False,
) -> int:
    """
    Copy multiple files into a destination directory.
    
    Args:
        sourceFiles: Sequence of source file paths
        destDir: Destination directory
        dryRun: If True, simulate actions without copying
        
    Returns:
        Number of files copied (or would be copied in dry run)
        
    Note:
        Uses shutil.copy2 to preserve timestamps
    """
    import shutil

    destDir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for src in sourceFiles:
        if not src.exists():
            continue

        destPath = destDir / src.name
        if dryRun:
            copied += 1
            continue

        shutil.copy2(src, destPath)
        copied += 1

    return copied


def extractExifDate(imagePath: Path) -> Optional[datetime.datetime]:
    """
    Extract EXIF DateTimeOriginal from an image file.
    
    Args:
        imagePath: Path to the image file
        
    Returns:
        datetime object if EXIF date is found, None otherwise
        
    Note:
        Requires PIL/Pillow. Returns None if PIL is not available.
    """
    try:
        from PIL import Image, ExifTags
        
        with Image.open(imagePath) as img:
            # Use modern getexif() if available (Pillow 6.0+), fallback to _getexif()
            try:
                exif = img.getexif()
            except AttributeError:
                exif = img._getexif() or {}
            
            if not exif:
                return None
            
            # Get DateTimeOriginal tag value
            # For modern getexif(), use ExifTags.Base enum
            # For legacy _getexif(), search TAGS dict
            date_str = None
            
            # Try modern approach first
            try:
                from PIL.ExifTags import Base
                date_str = exif.get(Base.DateTimeOriginal)
            except (ImportError, AttributeError):
                # Fallback to legacy approach
                for k, v in ExifTags.TAGS.items():
                    if v == "DateTimeOriginal" and k in exif:
                        date_str = exif[k]
                        break
            
            if date_str:
                # "YYYY:MM:DD HH:MM:SS" -> "YYYY-MM-DD HH:MM:SS"
                date_str = str(date_str).replace(":", "-", 2)
                return datetime.datetime.fromisoformat(date_str)
                
    except ImportError:
        # PIL/Pillow not available
        pass
    except Exception:
        # Any other error reading EXIF
        pass
    
    return None


def parseFilenameDate(filename: str) -> Optional[datetime.datetime]:
    """
    Parse date from filename using various patterns.
    
    Supported formats:
    - "082-1997-07" -> 1997-07-01 (year-month format with sequence prefix)
    - "049-1989-09-024" -> 1989-09-01 (year-month format with sequence)
    - "134-Gloucester 030502 003" -> 2003-05-02 (yymmdd format)
    - "something 1999-12 other" -> 1999-12-01 (year-month anywhere)
    - "prefix 030502" -> 2003-05-02 (yymmdd anywhere)
    - "photo_950315.jpg" -> 1995-03-15 (yymmdd with underscore)
    
    Args:
        filename: Filename to parse (without path)
        
    Returns:
        datetime object if date pattern is found, None otherwise
    """
    # Pattern 1: yyyy-mm format (e.g., "1997-07" or "082-1997-07")
    match = re.search(r'\b(19\d{2}|20\d{2})-(\d{2})\b', filename)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            try:
                return datetime.datetime(year, month, 1)
            except ValueError:
                pass
    
    # Pattern 2: yymmdd format (e.g., "030502" for 2003-05-02 or "950315" for 1995-03-15)
    # Look for 6-digit sequence that could be a date
    match = re.search(r'(?:^|[_\-\s])(\d{2})(\d{2})(\d{2})(?:[_\-\s.]|$)', filename)
    if match:
        yy = int(match.group(1))
        mm = int(match.group(2))
        dd = int(match.group(3))
        
        # Assume 2000s for years 00-30, 1900s for years 31-99
        year = 2000 + yy if yy <= 30 else 1900 + yy
        
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            try:
                return datetime.datetime(year, mm, dd)
            except ValueError:
                pass
    
    return None


def getImageDate(imagePath: Path) -> datetime.datetime:
    """
    Get the best available date for an image file.
    
    Priority order:
    1. EXIF DateTimeOriginal
    2. Date parsed from filename
    3. File modification time
    
    Args:
        imagePath: Path to the image file
        
    Returns:
        datetime object representing the image date
        
    Note:
        Always returns a valid datetime. Falls back to current time if file
        doesn't exist or all date extraction methods fail.
    """
    # Try EXIF first
    try:
        exifDate = extractExifDate(imagePath)
        if exifDate:
            return exifDate
    except Exception:
        pass
    
    # Try filename parsing
    try:
        filenameDate = parseFilenameDate(imagePath.name)
        if filenameDate:
            return filenameDate
    except Exception:
        pass
    
    # Fall back to file modification time
    try:
        return datetime.datetime.fromtimestamp(imagePath.stat().st_mtime)
    except (OSError, ValueError):
        # If file doesn't exist or stat fails, use current time as last resort
        return datetime.datetime.now()


def sortImagesByDate(images: List[Path]) -> List[Path]:
    """
    Sort images by their best available date.
    
    Uses getImageDate() to determine the date for each image,
    which tries EXIF, filename parsing, then modification time.
    
    Args:
        images: List of image paths to sort
        
    Returns:
        New list of image paths sorted by date (oldest first)
        
    Note:
        For better performance with large collections, this function
        processes all images sequentially. EXIF reading is only attempted
        once per image and results are not cached between calls.
    """
    imageWithDates = []
    for img in images:
        try:
            date = getImageDate(img)
            imageWithDates.append((img, date))
        except Exception:
            # If any error occurs, use current time as fallback
            imageWithDates.append((img, datetime.datetime.now()))
    
    imageWithDates.sort(key=lambda x: x[1])
    return [img for img, _ in imageWithDates]
