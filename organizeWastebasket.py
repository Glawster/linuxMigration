import os
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict

def parseSeasonEpisode(filename: str):
    """
    Extract title, SddEdd, and name from filename.
    Example: title.S00E07.name0001.avi
    """
    # Main pattern
    pattern = r'^(?P<title>.+?)\.(?P<seasonEpisode>S\d{2}E\d{2})\.(?P<name>.+?)(?:\d+)?\.(?P<ext>[^.]+)$'
    match = re.match(pattern, filename, re.IGNORECASE)
    
    if match:
        title = match.group('title').strip()
        seasonEpisode = match.group('seasonEpisode').upper()
        name = match.group('name').strip()
        return title, seasonEpisode, name
    
    # Fallback pattern
    fallbackPattern = r'^(?P<title>.+?)\.(?P<seasonEpisode>S\d{2}E\d{2})'
    match2 = re.search(fallbackPattern, filename, re.IGNORECASE)
    if match2:
        title = match2.group('title').strip()
        seasonEpisode = match2.group('seasonEpisode').upper()
        
        remaining = filename[match2.end():].strip('.')
        namePart = re.split(r'\d+\.', remaining)[0] if re.search(r'\d', remaining) else remaining
        name = re.sub(r'\.(mp4|avi|mkv|mov)$', '', namePart, flags=re.IGNORECASE).strip()
        
        if not name or name.lower() in ["unknown", ""]:
            name = "Unknown"
        return title, seasonEpisode, name
    
    return None, None, None


def groupFilesByFolder(sourceDir: str, confirm: bool = False):
    """
    Group files into folders like: title.S00E07.name/
    """
    sourcePath = Path(sourceDir)
    if not sourcePath.exists():
        print(f"Error: Directory {sourceDir} does not exist!")
        return

    folderGroups = defaultdict(list)

    print("Scanning files...\n")

    for filePath in sourcePath.rglob('*.*'):
        if filePath.is_file() and filePath.parent.name != "Proxy":
            filename = filePath.name
            
            title, seasonEpisode, name = parseSeasonEpisode(filename)
            
            if title and seasonEpisode:
                if name and name.lower() not in ["unknown", ""]:
                    folderName = f"{title}.{seasonEpisode}.{name}"
                else:
                    folderName = f"{title}.{seasonEpisode}.Unknown"
                
                folderGroups[folderName].append(filePath)
            else:
                print(f"Could not parse: {filename}")

    if not folderGroups:
        print("No files found to organize.")
        return

    # Show summary
    print(f"Found {len(folderGroups)} groups to create:\n")
    for folderName, files in sorted(folderGroups.items()):
        print(f"  {folderName}  ({len(files)} files)")

    # Ask for confirmation if not using --confirm
    if not confirm:
        print("\n" + "="*60)
        print("This is a DRY RUN. No files will be moved.")
        print("To actually move the files, run the script with --confirm flag:")
        print(f"    python {Path(sys.argv[0]).name} --confirm")
        print("="*60)
        return

    # === ACTUAL MOVE (only runs with --confirm) ===
    print("\n" + "="*60)
    print("CONFIRMED - Starting to organize files...")
    print("="*60)

    for folderName, files in folderGroups.items():
        targetFolder = sourcePath / folderName
        targetFolder.mkdir(exist_ok=True)
        print(f"\nCreated folder: {folderName}")

        for filePath in files:
            dest = targetFolder / filePath.name
            if dest.exists():
                print(f"  Skipping (already exists): {filePath.name}")
            else:
                try:
                    shutil.move(str(filePath), str(dest))
                    print(f"  Moved: {filePath.name}")
                except Exception as e:
                    print(f"  Error moving {filePath.name}: {e}")

    print("\n" + "="*60)
    print(f"Organization completed! {len(folderGroups)} folders created.")
    print("="*60)


if __name__ == "__main__":
    # Handle command line argument
    confirm = False
    if len(sys.argv) > 1 and sys.argv[1] in ["--confirm", "-c", "--yes"]:
        confirm = True

    print(".wastebasket File Organizer")
    print("-" * 70)
    
    groupFilesByFolder(".", confirm=confirm)