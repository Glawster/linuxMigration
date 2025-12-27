import os
import shutil
import sys
import argparse

# ==========================================
# CONFIG (camelCase)
# ==========================================

# Root folder containing all style folders
baseDir = r"/mnt/myVideo/Adult/tumblrForMovie"

# Kohya repeat count (e.g. 10 will create subfolders like '10_wedding')
repeatCount = 10

# Image extensions to process
imageExts = {".jpg", ".jpeg", ".png", ".webp"}

# Caption template
captionTemplate = "a photograph in {token} style"
# ==========================================


def isImageFile(filename: str) -> bool:
    """Return True if file is an image based on extension."""
    return os.path.splitext(filename)[1].lower() in imageExts


def ensureKohyaFolder(styleRoot: str, styleName: str, dry_run: bool = False) -> str:
    """
    Create and return the path to the Kohya training folder like:
        '10_styleName'
    """
    kohyaFolderName = f"{repeatCount}_{styleName}"
    kohyaFolderPath = os.path.join(styleRoot, kohyaFolderName)
    if not dry_run:
        os.makedirs(kohyaFolderPath, exist_ok=True)
    return kohyaFolderPath


def processStyleFolder(styleRoot: str, dry_run: bool = False):
    """
    Processes one style folder such as:
        /mnt/myVideo/Adult/tumblrForMovie/wedding
    """
    styleName = os.path.basename(styleRoot)

    # Token used inside caption, e.g. <wedding_style>
    tokenName = f"{styleName.replace(' ', '_')}"

    kohyaSubdir = ensureKohyaFolder(styleRoot, styleName, dry_run=dry_run)

    print(f"\nProcessing: {styleRoot}")
    print(f"  Kohya folder: {kohyaSubdir}")
    print(f"  Token used: {tokenName}")

    # Process all files in the style root directory
    for entry in list(os.scandir(styleRoot)):
        if entry.is_dir():
            # Skip the Kohya folder itself and any other unrelated folders
            if entry.path == kohyaSubdir:
                continue
            print(f"  Skipping subfolder: {entry.name}")
            continue

        filename = entry.name
        filePath = entry.path

        if not isImageFile(filename):
            continue

        destImagePath = os.path.join(kohyaSubdir, filename)

        # Move image file
        if os.path.abspath(filePath) != os.path.abspath(destImagePath):
            print(f"  Moving image: {filename}")
            if not dry_run:
                shutil.move(filePath, destImagePath)
        else:
            print(f"  Image already in correct location: {filename}")

        # Caption handling
        baseName, _ = os.path.splitext(filename)
        srcCaptionPath = os.path.join(styleRoot, baseName + ".txt")
        destCaptionPath = os.path.join(kohyaSubdir, baseName + ".txt")

        # Caption already exists → skip
        if os.path.exists(destCaptionPath):
            print(f"    Caption already exists: {destCaptionPath}")
            continue

        # If caption exists in the top-level folder → move it
        if os.path.exists(srcCaptionPath):
            print(f"    Moving caption: {baseName}.txt")
            if not dry_run:
                shutil.move(srcCaptionPath, destCaptionPath)
            continue

        # Otherwise create a new caption
        print(f"    Creating caption: {baseName}.txt")
        if not dry_run:
            captionText = captionTemplate.format(token=tokenName)
            with open(destCaptionPath, "w", encoding="utf-8") as f:
                f.write(captionText)


def undoKohyaFolders(styleNameFilter=None, dry_run: bool = False):
    """
    Restore the directory structure back to a flat structure by moving all files
    from Kohya subfolders (e.g., '10_styleName') back to the parent style folder.
    
    Args:
        styleNameFilter: Optional style name to process only that specific style folder.
                        If None, processes all style folders under baseDir.
        dry_run: If True, show what would be done without actually doing it.
    """
    print(f"Undoing Kohya structure in: {baseDir}")

    if not os.path.isdir(baseDir):
        print("ERROR: baseDir does not exist or is not a directory.")
        return

    if styleNameFilter:
        # Process only the specified style folder
        styleRoot = os.path.join(baseDir, styleNameFilter)
        if not os.path.isdir(styleRoot):
            print(f"ERROR: Style folder '{styleNameFilter}' not found at {styleRoot}")
            return
        styleFolders = [styleRoot]
    else:
        # Process all style folders under baseDir
        styleFolders = [entry.path for entry in os.scandir(baseDir) if entry.is_dir()]

    for styleRoot in styleFolders:
        styleName = os.path.basename(styleRoot)

        # Look for Kohya folder like '10_styleName'
        kohyaFolderName = f"{repeatCount}_{styleName}"
        kohyaFolderPath = os.path.join(styleRoot, kohyaFolderName)

        if not os.path.exists(kohyaFolderPath):
            print(f"\nNo Kohya folder found for '{styleName}', skipping.")
            continue

        print(f"\nRestoring: {styleRoot}")
        print(f"  Moving files from: {kohyaFolderPath}")

        # Move all files from Kohya subfolder back to parent
        for fileEntry in list(os.scandir(kohyaFolderPath)):
            if fileEntry.is_file():
                srcPath = fileEntry.path
                destPath = os.path.join(styleRoot, fileEntry.name)

                # If file already exists in parent, skip
                if os.path.exists(destPath):
                    print(f"  File already exists in parent folder: {fileEntry.name}, skipping.")
                    continue

                print(f"  Moving: {fileEntry.name}")
                if not dry_run:
                    shutil.move(srcPath, destPath)

        # Remove the now-empty Kohya folder
        if not dry_run:
            try:
                os.rmdir(kohyaFolderPath)
                print(f"  Removed empty folder: {kohyaFolderName}")
            except OSError as e:
                print(f"  WARNING: Could not remove folder {kohyaFolderName}: {e}")
        else:
            print(f"  Would remove empty folder: {kohyaFolderName}")

    print("\nFinished! Your folders have been restored to flat structure.")


def processStyleFolders(styleNameFilter=None, dry_run: bool = False):
    """
    Process style folders to create Kohya structure.
    
    Args:
        styleNameFilter: Optional style name to process only that specific style folder.
                        If None, processes all style folders under baseDir.
        dry_run: If True, show what would be done without actually doing it.
    """
    print(f"Scanning: {baseDir}")

    if not os.path.isdir(baseDir):
        print("ERROR: baseDir does not exist or is not a directory.")
        return

    if styleNameFilter:
        # Process only the specified style folder
        styleRoot = os.path.join(baseDir, styleNameFilter)
        if not os.path.isdir(styleRoot):
            print(f"ERROR: Style folder '{styleNameFilter}' not found at {styleRoot}")
            return
        styleFolders = [styleRoot]
    else:
        # Process all style folders under baseDir
        styleFolders = [entry.path for entry in os.scandir(baseDir) if entry.is_dir()]

    for styleRoot in styleFolders:
        processStyleFolder(styleRoot, dry_run=dry_run)

    print("\nFinished! Your folders are now Kohya-ready.")


def main():
    parser = argparse.ArgumentParser(
        description="Create or restore Kohya training folder structure"
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Restore folders from Kohya structure back to flat structure"
    )
    parser.add_argument(
        "--style",
        type=str,
        default=None,
        help="Process only a specific style folder (e.g., 'wedding'). If not provided, processes all style folders under baseDir."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually performing any operations"
    )

    args = parser.parse_args()

    if args.dry_run:
        print("[DRY RUN MODE] - No files will be modified")
    
    if args.style:
        print(f"Processing style: {args.style}")

    if args.undo:
        undoKohyaFolders(styleNameFilter=args.style, dry_run=args.dry_run)
    else:
        processStyleFolders(styleNameFilter=args.style, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
