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


def extractExifDate(imagePath: Path, prefix: str = "...") -> tuple[Optional[datetime.datetime], Optional[str]]:
    """
    Extract EXIF date/time from an image file.
    
    Tries multiple EXIF date/time tags in order of preference:
    1. DateTimeOriginal (36867) - when photo was taken
    2. DateTimeDigitized (36868) - when photo was digitized
    3. DateTime (306) - file modification date/time
    
    Args:
        imagePath: Path to the image file
        prefix: Logging prefix for debug messages
        
    Returns:
        Tuple of (datetime object, tag name) if EXIF date is found, (None, None) otherwise
        
    Note:
        Requires PIL/Pillow. Returns (None, None) if PIL is not available.
    """
    try:
        from PIL import Image, ExifTags
        print(f"{prefix} exif-debug: PIL imported successfully")
        
        with Image.open(imagePath) as img:
            print(f"{prefix} exif-debug: Image opened: {imagePath.name}")
            
            # Use modern getexif() if available (Pillow 6.0+), fallback to _getexif()
            exif = None
            try:
                exif = img.getexif()
                print(f"{prefix} exif-debug: getexif() succeeded, exif data: {bool(exif)}")
            except AttributeError as e:
                print(f"{prefix} exif-debug: getexif() not available: {e}")
                # Try legacy _getexif()
                try:
                    exif = img._getexif()
                    print(f"{prefix} exif-debug: _getexif() succeeded, exif data: {bool(exif)}")
                except AttributeError as e2:
                    print(f"{prefix} exif-debug: _getexif() failed: {e2}")
                    pass
            
            if not exif:
                print(f"{prefix} exif-debug: No EXIF data found in image")
                return (None, None)
            
            print(f"{prefix} exif-debug: EXIF data type: {type(exif)}")
            print(f"{prefix} exif-debug: EXIF keys count: {len(exif) if hasattr(exif, '__len__') else 'N/A'}")
            
            # Show all EXIF tags for debugging
            if hasattr(exif, 'keys'):
                all_tags = list(exif.keys())
                print(f"{prefix} exif-debug: All EXIF tag IDs in main IFD: {all_tags}")
                # Also show the tag names if we can look them up
                tag_names = []
                for tag_id in all_tags[:20]:  # Limit to first 20 for readability
                    tag_name = ExifTags.TAGS.get(tag_id, f"Unknown-{tag_id}")
                    tag_names.append(f"{tag_id}={tag_name}")
                print(f"{prefix} exif-debug: EXIF tag names in main IFD: {tag_names}")
            
            # Try to get the Exif IFD sub-directory which contains DateTimeOriginal
            # This is where the issue likely is - DateTimeOriginal is in the Exif IFD, not the main IFD
            exif_ifd = None
            try:
                if hasattr(exif, 'get_ifd'):
                    from PIL.ExifTags import IFD
                    exif_ifd = exif.get_ifd(IFD.Exif)
                    if exif_ifd:
                        print(f"{prefix} exif-debug: Exif IFD found with {len(exif_ifd)} tags")
                        exif_ifd_tags = list(exif_ifd.keys())
                        print(f"{prefix} exif-debug: Exif IFD tag IDs: {exif_ifd_tags}")
                        exif_ifd_names = []
                        for tag_id in exif_ifd_tags[:20]:
                            tag_name = ExifTags.TAGS.get(tag_id, f"Unknown-{tag_id}")
                            exif_ifd_names.append(f"{tag_id}={tag_name}")
                        print(f"{prefix} exif-debug: Exif IFD tag names: {exif_ifd_names}")
            except Exception as e:
                print(f"{prefix} exif-debug: Could not access Exif IFD: {e}")
            
            # Try multiple date/time tags in order of preference
            # Most relevant first: DateTimeOriginal, DateTimeDigitized, DateTime
            date_tags_to_try = [
                ("DateTimeOriginal", 36867, "when photo was taken"),
                ("DateTimeDigitized", 36868, "when photo was digitized"),
                ("DateTime", 306, "file modification date"),
            ]
            
            dateStr = None
            tagUsed = None
            
            # For modern getexif() - it returns a dict-like object
            if hasattr(exif, 'get'):
                print(f"{prefix} exif-debug: EXIF has 'get' method")
                
                # Try each date tag in order of preference
                for tag_name, tag_id, tag_desc in date_tags_to_try:
                    if dateStr:
                        break  # Already found a date
                    
                    print(f"{prefix} exif-debug: Trying {tag_name} (tag {tag_id}): {tag_desc}")
                    
                    # First, try the Exif IFD if we have it (this is where DateTimeOriginal usually lives)
                    if exif_ifd and tag_id in [36867, 36868]:  # These tags are in Exif IFD
                        if tag_id in exif_ifd:
                            dateStr = exif_ifd[tag_id]
                            tagUsed = tag_name
                            print(f"{prefix} exif-debug: Found via Exif IFD tag ID {tag_id} ({tag_name}): {dateStr}")
                            continue
                        else:
                            print(f"{prefix} exif-debug: Tag {tag_id} ({tag_name}) not in Exif IFD")
                    
                    # Try using ExifTags.Base enum if available (Pillow 9.0+)
                    try:
                        from PIL.ExifTags import Base
                        base_attr = getattr(Base, tag_name, None)
                        if base_attr:
                            dateStr = exif.get(base_attr)
                            if dateStr:
                                tagUsed = tag_name
                                print(f"{prefix} exif-debug: Found via Base.{tag_name}: {dateStr}")
                    except (ImportError, AttributeError) as e:
                        print(f"{prefix} exif-debug: Base enum not available: {e}")
                        pass
                    
                    # If that didn't work, try the numeric tag ID directly in main exif
                    if not dateStr:
                        if tag_id in exif:
                            dateStr = exif[tag_id]
                            tagUsed = tag_name
                            print(f"{prefix} exif-debug: Found via main IFD tag ID {tag_id} ({tag_name}): {dateStr}")
                        else:
                            print(f"{prefix} exif-debug: Tag {tag_id} ({tag_name}) not in main IFD")
            else:
                print(f"{prefix} exif-debug: EXIF doesn't have 'get' method")
            
            if dateStr:
                print(f"{prefix} exif-debug: Using {tagUsed} for date")
                print(f"{prefix} exif-debug: Raw date string: {dateStr}")
                # "YYYY:MM:DD HH:MM:SS" -> "YYYY-MM-DD HH:MM:SS"
                dateStr = str(dateStr).replace(":", "-", 2)
                print(f"{prefix} exif-debug: Converted date string: {dateStr}")
                try:
                    result = datetime.datetime.fromisoformat(dateStr)
                    print(f"{prefix} exif-debug: Parsed with fromisoformat: {result}")
                    return (result, tagUsed)
                except ValueError as e:
                    print(f"{prefix} exif-debug: fromisoformat failed: {e}")
                    # Fallback to strptime if fromisoformat fails
                    try:
                        result = datetime.datetime.strptime(dateStr, "%Y-%m-%d %H:%M:%S")
                        print(f"{prefix} exif-debug: Parsed with strptime: {result}")
                        return (result, tagUsed)
                    except ValueError as e2:
                        print(f"{prefix} exif-debug: strptime also failed: {e2}")
                        pass
            else:
                print(f"{prefix} exif-debug: No date/time tags found in EXIF")
                
    except ImportError as e:
        # PIL/Pillow not available
        print(f"{prefix} exif-debug: PIL import failed: {e}")
        pass
    except Exception as e:
        # Any other error reading EXIF
        print(f"{prefix} exif-debug: Unexpected exception: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        pass
    
    print(f"{prefix} exif-debug: Returning (None, None)")
    return (None, None)


def updateExifDate(imagePath: Path, date: datetime.datetime) -> bool:
    """
    Update the EXIF DateTimeOriginal field in an image file.
    
    Args:
        imagePath: Path to the image file to update
        date: datetime to write to EXIF
        
    Returns:
        True if EXIF was successfully updated, False otherwise
        
    Note:
        Requires PIL/Pillow and piexif library. Only works with JPEG files.
        Returns False if dependencies are not available or file format is unsupported.
    """
    try:
        import piexif
        from PIL import Image
        
        # Only support JPEG files for EXIF writing
        if imagePath.suffix.lower() not in {'.jpg', '.jpeg'}:
            return False
        
        # Format date as EXIF expects: "YYYY:MM:DD HH:MM:SS"
        exif_date_str = date.strftime("%Y:%m:%d %H:%M:%S")
        
        try:
            # Try to load existing EXIF data
            exif_dict = piexif.load(str(imagePath))
        except Exception:
            # If no EXIF or corrupted, create new EXIF dict
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}, "thumbnail": None}
        
        # Update DateTimeOriginal in EXIF IFD
        exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = exif_date_str
        exif_dict["Exif"][piexif.ExifIFD.DateTimeDigitized] = exif_date_str
        
        # Also update DateTime in main IFD
        exif_dict["0th"][piexif.ImageIFD.DateTime] = exif_date_str
        
        # Convert dict to bytes
        exif_bytes = piexif.dump(exif_dict)
        
        # Save image with updated EXIF using context manager
        with Image.open(imagePath) as img:
            img.save(imagePath, exif=exif_bytes, quality=95)
        
        return True
        
    except ImportError:
        # piexif or PIL not available
        return False
    except Exception:
        # Any other error writing EXIF
        return False


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
    - "1989_07_06 22_33_24.jpg" -> 1989-07-06 (yyyy_mm_dd format)
    - "1987_02.1.png" -> 1987-02-01 (yyyy_mm format)
    - "Christmas 2007" -> 2007-01-01 (year alone)
    - "20191020" -> 2019-10-20 (yyyymmdd format)
    
    Args:
        filename: Filename to parse (without path)
        
    Returns:
        datetime object if date pattern is found, None otherwise
    """
    # Pattern 1: yyyymmdd format (8 digits) - e.g., "20191020" for 2019-10-20
    match = re.search(r'\b(19\d{2}|20\d{2})(\d{2})(\d{2})\b', filename)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return datetime.datetime(year, month, day)
            except ValueError:
                pass
    
    # Pattern 2: yyyy_mm_dd or yyyy-mm-dd format (with time optional)
    match = re.search(r'\b(19\d{2}|20\d{2})[_\-](\d{2})[_\-](\d{2})\b', filename)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                return datetime.datetime(year, month, day)
            except ValueError:
                pass
    
    # Pattern 3: yyyy-mm or yyyy_mm format (e.g., "1997-07" or "1987_02")
    match = re.search(r'\b(19\d{2}|20\d{2})[_\-](\d{1,2})(?:\b|\.)', filename)
    if match:
        year = int(match.group(1))
        month = int(match.group(2))
        if 1 <= month <= 12:
            try:
                return datetime.datetime(year, month, 1)
            except ValueError:
                pass
    
    # Pattern 4: Month name followed by 2-digit year (e.g., "july 09" -> 2009-07)
    month_names = {
        'jan': 1, 'january': 1,
        'feb': 2, 'february': 2,
        'mar': 3, 'march': 3,
        'apr': 4, 'april': 4,
        'may': 5,
        'jun': 6, 'june': 6,
        'jul': 7, 'july': 7,
        'aug': 8, 'august': 8,
        'sep': 9, 'september': 9, 'sept': 9,
        'oct': 10, 'october': 10,
        'nov': 11, 'november': 11,
        'dec': 12, 'december': 12
    }
    
    for month_name, month_num in month_names.items():
        # Match "july 09" or "july09"
        pattern = rf'\b{month_name}\s*(\d{{2}})\b'
        match = re.search(pattern, filename, re.IGNORECASE)
        if match:
            yy = int(match.group(1))
            year = 2000 + yy if yy <= 50 else 1900 + yy
            try:
                return datetime.datetime(year, month_num, 1)
            except ValueError:
                pass
    
    # Pattern 5: Just a 4-digit year (e.g., "Christmas 2007" -> 2007-01-01)
    match = re.search(r'\b(19\d{2}|20\d{2})\b', filename)
    if match:
        year = int(match.group(1))
        try:
            return datetime.datetime(year, 1, 1)
        except ValueError:
            pass
    
    # Pattern 6: yymmdd format (e.g., "030502" for 2003-05-02 or "950315" for 1995-03-15)
    # Look for 6-digit sequence that could be a date
    match = re.search(r'(?:^|[_\-\s])(\d{2})(\d{2})(\d{2})(?:[_\-\s.]|$)', filename)
    if match:
        yy = int(match.group(1))
        mm = int(match.group(2))
        dd = int(match.group(3))
        
        # Assume 2000s for years 00-50, 1900s for years 51-99
        # This will work correctly until 2051
        year = 2000 + yy if yy <= 50 else 1900 + yy
        
        if 1 <= mm <= 12 and 1 <= dd <= 31:
            try:
                return datetime.datetime(year, mm, dd)
            except ValueError:
                pass
    
    return None


def getImageDate(imagePath: Path, updateExif: bool = False, prefix: str = "...") -> datetime.datetime:
    """
    Get the best available date for an image file.
    
    Priority order:
    1. EXIF DateTimeOriginal
    2. Date parsed from filename
    3. File modification time
    
    Args:
        imagePath: Path to the image file
        updateExif: If True, write filename date to EXIF when no EXIF date exists
        prefix: Logging prefix for debug messages
        
    Returns:
        datetime object representing the image date
        
    Note:
        Always returns a valid datetime. Falls back to current time if file
        doesn't exist or all date extraction methods fail.
        
        When updateExif=True and a date is found in the filename but not in EXIF,
        the function will attempt to write that date to the image's EXIF data.
        This requires the piexif library and only works with JPEG files.
    """
    # Try EXIF first
    try:
        exifDate, tagName = extractExifDate(imagePath, prefix=prefix)
        if exifDate:
            tagLabel = f"EXIF {tagName}" if tagName else "EXIF"
            print(f"{prefix} date: {imagePath.name} -> {exifDate.strftime('%Y-%m-%d')} [{tagLabel}]")
            return exifDate
    except (OSError, ValueError, ImportError):
        pass
    
    # Try filename parsing
    try:
        filenameDate = parseFilenameDate(imagePath.name)
        if filenameDate:
            print(f"{prefix} date: {imagePath.name} -> {filenameDate.strftime('%Y-%m-%d')} [filename pattern]")
            # If requested, try to update EXIF with filename date
            if updateExif:
                try:
                    if updateExifDate(imagePath, filenameDate):
                        print(f"{prefix} exif: {imagePath.name} <- {filenameDate.strftime('%Y-%m-%d')} [JPEG EXIF updated]")
                except (OSError, ValueError, ImportError):
                    pass  # Continue even if EXIF update fails
            return filenameDate
    except (ValueError, OSError):
        pass
    
    # Fall back to file modification time
    try:
        mtime = datetime.datetime.fromtimestamp(imagePath.stat().st_mtime)
        print(f"{prefix} date: {imagePath.name} -> {mtime.strftime('%Y-%m-%d')} [file modification time]")
        return mtime
    except (OSError, ValueError):
        # If file doesn't exist or stat fails, use current time as last resort
        now = datetime.datetime.now()
        print(f"{prefix} date: {imagePath.name} -> {now.strftime('%Y-%m-%d')} [current time - fallback]")
        return now


def sortImagesByDate(images: List[Path], updateExif: bool = False, prefix: str = "...") -> List[Tuple[Path, datetime.datetime]]:
    """
    Sort images by their best available date.
    
    Uses getImageDate() to determine the date for each image,
    which tries EXIF, filename parsing, then modification time.
    
    Args:
        images: List of image paths to sort
        updateExif: If True, write filename dates to EXIF when no EXIF date exists
        prefix: Logging prefix for debug messages
        
    Returns:
        New list of tuples (image_path, date) sorted by date (oldest first)
        
    Note:
        For better performance with large collections, this function
        processes all images sequentially. EXIF reading is only attempted
        once per image and results are not cached between calls.
        
        When updateExif=True, EXIF data will be updated for images that have
        dates in their filenames but no EXIF DateTimeOriginal field. This
        requires the piexif library and only works with JPEG files.
    """
    imageWithDates = []
    for img in images:
        try:
            date = getImageDate(img, updateExif=updateExif, prefix=prefix)
            imageWithDates.append((img, date))
        except (OSError, ValueError, ImportError):
            # If any error occurs, use current time as fallback
            now = datetime.datetime.now()
            print(f"{prefix} date: {img.name} -> {now.strftime('%Y-%m-%d')} [error fallback]")
            imageWithDates.append((img, now))
    
    imageWithDates.sort(key=lambda x: x[1])
    return imageWithDates
