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

import os
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
