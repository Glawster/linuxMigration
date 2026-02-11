# Additional Copilot Instructions for linuxMigration

## Project-Specific Information

This file contains project-specific details for the **linuxMigration** repository. For generic Bash scripting and Python development guidelines, see `copilot-instructions.md`.

## Project Overview

**linuxMigration** contains scripts and tools for migrating and organizing a Linux home directory from Pop!_OS to Ubuntu. It includes recovery pipelines for photos/videos, system configuration management, and home directory organization.

### Key Features
- Home directory migration scripts (Bash)
- Photo/video recovery pipeline (Python)
- System configuration management
- Duplicate detection and filtering
- Black/corrupt image detection
- Integration with kohyaConfig shared configuration system

## Technology Stack

- **Bash**: Shell scripts for system-level operations
- **Python**: 3.8+ for image/video processing
- **Libraries**: imagehash, Pillow, pathlib, argparse
- **Platform**: Ubuntu 22.04+, Pop!_OS (source)

## Repository Structure

```
linuxMigration/
├── .github/
│   ├── copilot-instructions.md           # Generic guidelines (synced from Glawster/organiseMyProjects)
│   └── additional-copilot-instructions.md # Project-specific (this file)
├── recoveryTools/                        # Photo/video recovery pipeline (subproject)
│   ├── recoveryPipeline.py               # Main recovery orchestration
│   ├── dedupeImages.py                   # Perceptual hash image deduplication
│   ├── dedupeVideos.py                   # Video deduplication
│   ├── filterBlackImages.py              # Black/corrupt image removal
│   ├── sortImagesByResolution.py         # Organize by resolution
│   ├── sortVideosByDuration.py           # Organize by duration
│   ├── buildImageTimeline.py             # Timeline organization
│   ├── cleanRecoveredFiles.py            # Post-recovery cleanup
│   ├── flattenRecovery.py                # Flatten directory structure
│   ├── recoveryCommon.py                 # Shared utilities
│   └── requirements.txt                  # Python dependencies
├── kohyaTools/                           # Image processing & AI training (subproject)
│   ├── kohyaConfig.py                    # Shared configuration system
│   ├── kohyaUtils.py                     # Common utilities
│   ├── createKohyaDirs.py                # Directory setup
│   ├── trainKohya.py                     # LoRA training orchestration
│   ├── img2ImgComfy.py                   # Image-to-image processing
│   ├── batchImg2ImgComfy.py              # Batch processing
│   ├── txt2imgComfy.py                   # Text-to-image generation
│   ├── remoteImg2ImgComfy.py             # Remote processing
│   ├── promptFromPhoto.py                # Prompt generation
│   ├── inspectLora.py                    # LoRA inspection
│   ├── copyToComfyUI.py                  # ComfyUI integration
│   ├── migrateKohyaRemoveDate.py         # Migration utility
│   └── documentation/                    # Tool documentation
├── runpodTools/                          # RunPod cloud setup (subproject)
│   ├── runpodBootstrap.sh                # Remote-side orchestrator
│   ├── createPod.sh                      # Pod creation
│   ├── lib/                              # Reusable functions
│   │   ├── common.sh                     # Logging, run, die helpers
│   │   ├── ssh.sh                        # SSH utilities
│   │   ├── apt.sh                        # Package management
│   │   ├── conda.sh                      # Conda setup
│   │   ├── git.sh                        # Git operations
│   │   ├── workspace.sh                  # State tracking
│   │   └── diagnostics.sh                # System diagnostics
│   ├── steps/                            # Bootstrap steps
│   │   ├── 10_diagnostics.sh             # System checks
│   │   ├── 20_base_tools.sh              # Base packages
│   │   ├── 30_conda.sh                   # Miniconda setup
│   │   ├── 40_comfyui.sh                 # ComfyUI setup
│   │   ├── 50_kohya.sh                   # Kohya SS setup
│   │   └── 60_upload_models.sh           # Model uploads
│   ├── test/                             # Test suite
│   ├── documentation/                    # RunPod docs
│   └── README.md                         # Full documentation
├── sidecarEditor/                        # EXIF metadata editor
├── organiseHome.sh                       # Main home directory migration
├── organiseOfficeFiles.sh                # Office document organization
├── organiseWindowsHome.sh                # Windows migration
├── pdfFiler.sh                           # PDF organization
├── installLinuxApps.sh                   # Application installer
├── setupBattlenetPrefix.sh               # Gaming setup
└── [other scripts]                       # Various utilities
```

## Bash Scripts

### organiseHome.sh - Main Migration Script

Primary script for organizing home directory structure.

**Key Features:**
- Creates standard directory structure
- Moves files to appropriate locations
- Preserves original structure where needed
- Interactive confirmations for destructive operations
- Comprehensive logging

**Safety Patterns:**
```bash
#!/usr/bin/env bash
set -euo pipefail

# Helper function for safe directory creation
makeDir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo "creating directory: $dir"
        mkdir -p "$dir"
    fi
}

# Safe file move with existence check
moveIfExists() {
    local src="$1"
    local dest="$2"
    if [ -e "$src" ]; then
        echo "moving: $src -> $dest"
        mv -i "$src" "$dest/"
    else
        echo "skipping (not found): $src"
    fi
}
```

**Usage:**
```bash
# Run from home directory
cd ~
bash /path/to/organiseHome.sh

# Or with explicit paths
bash organiseHome.sh --source /old/home --target /new/home
```

**Directory Structure Created:**
```
~/
├── Documents/
│   ├── Work/
│   ├── Personal/
│   └── Archive/
├── Media/
│   ├── Photos/
│   ├── Videos/
│   └── Music/
├── Development/
│   ├── Projects/
│   └── Tools/
└── [other standard directories]
```

### Common Bash Patterns

#### Progress Indicators
```bash
echo "=== Starting Home Directory Organization ==="
echo "source: $sourceDir"
echo "target: $targetDir"

echo "...creating directory structure"
makeDir "$targetDir/Documents"
makeDir "$targetDir/Media"

echo "...moving files"
moveIfExists "$sourceDir/file.txt" "$targetDir/Documents"

echo "=== Organization Complete ==="
```

#### Error Handling
```bash
# Check prerequisites
if [ ! -d "$sourceDir" ]; then
    echo "Error: Source directory does not exist: $sourceDir"
    exit 1
fi

# Validate before destructive operations
if [ -e "$targetFile" ]; then
    read -p "File exists. Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipping: $targetFile"
        continue
    fi
fi
```

## Subprojects

This repository contains three major subprojects, each with its own focus and tooling:

1. **recoveryTools**: Photo/video recovery pipeline for PhotoRec output
2. **kohyaTools**: Image processing and AI model training workflows
3. **runpodTools**: Cloud computing environment bootstrap for RunPod

### recoveryTools - Photo/Video Recovery Pipeline

All Python tools follow a consistent recovery pipeline pattern: work in-place, move filtered items to subdirectories.

### Common Patterns

#### Argument Parsing
```python
#!/usr/bin/env python3
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Tool description")
    parser.add_argument("--source", required=True, help="Source directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    parser.add_argument("--threshold", type=float, default=5.0, help="Detection threshold")
    args = parser.parse_args()
    
    # Validate path
    try:
        sourceDir = Path(args.source).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise SystemExit(f"Error resolving path: {e}")
    
    if not sourceDir.is_dir():
        raise SystemExit(f"Directory does not exist: {sourceDir}")
    
    # Process
    processDirectory(sourceDir, args.dry_run, args.threshold)

if __name__ == "__main__":
    main()
```

#### In-Place Processing Pattern
```python
def processDirectory(sourceDir, dryRun=False):
    """Process files in-place, moving filtered items to subdirectory."""
    
    # Create filtered directory
    filteredDir = sourceDir / "FilteredImages"
    if not dryRun:
        filteredDir.mkdir(exist_ok=True)
    
    # Process files
    for imageFile in sourceDir.glob("*.jpg"):
        if shouldFilter(imageFile):
            targetPath = filteredDir / imageFile.name
            
            if dryRun:
                print(f"Would move: {imageFile} -> {targetPath}")
            else:
                imageFile.rename(targetPath)
                print(f"Moved: {imageFile.name}")
```

### removeBlackImages.py

Detects and removes black/corrupt images using histogram analysis.

**Features:**
- Histogram-based black image detection
- Configurable threshold
- Moves black images to `BlackImages/` subdirectory
- Dry-run support
- Preserves directory structure

**Usage:**
```bash
# Basic usage
python3 removeBlackImages.py --source ~/Photos

# With custom threshold
python3 removeBlackImages.py --source ~/Photos --threshold 0.95

# Dry run to preview
python3 removeBlackImages.py --source ~/Photos --dry-run
```

**Detection Algorithm:**
```python
from PIL import Image
import numpy as np

def isBlackImage(imagePath, threshold=0.90):
    """Check if image is predominantly black."""
    try:
        img = Image.open(imagePath).convert('L')  # Grayscale
        histogram = img.histogram()
        
        # Count dark pixels (0-25 intensity)
        darkPixels = sum(histogram[:26])
        totalPixels = sum(histogram)
        
        blackRatio = darkPixels / totalPixels
        return blackRatio > threshold
    except Exception as e:
        print(f"Error processing {imagePath}: {e}")
        return False
```

### findDuplicateImages.py

Finds duplicate images using perceptual hashing.

**Features:**
- Uses `imagehash` library for perceptual hashing
- Configurable hash size and threshold
- Groups similar images
- Moves duplicates to `Duplicates/` subdirectory
- Keeps original, moves duplicates

**Usage:**
```bash
# Basic usage
python3 findDuplicateImages.py --source ~/Photos

# With custom sensitivity
python3 findDuplicateImages.py --source ~/Photos --hash-size 16 --threshold 5

# Dry run
python3 findDuplicateImages.py --source ~/Photos --dry-run
```

**Hashing Strategy:**
```python
import imagehash
from PIL import Image

def hashImage(imagePath, hashSize=8):
    """Generate perceptual hash for image."""
    img = Image.open(imagePath)
    phash = imagehash.phash(img, hash_size=hashSize)
    return phash

def findDuplicates(sourceDir, hashSize=8, threshold=5):
    """Find duplicate images by hash similarity."""
    hashes = {}
    duplicates = {}
    
    for imageFile in sourceDir.glob("*.jpg"):
        imgHash = hashImage(imageFile, hashSize)
        
        # Check for similar hashes
        for existingHash, existingFile in hashes.items():
            if imgHash - existingHash <= threshold:
                # Found duplicate
                duplicates.setdefault(existingFile, []).append(imageFile)
                break
        else:
            # New unique image
            hashes[imgHash] = imageFile
    
    return duplicates
```

### findDuplicateVideos.py

Finds duplicate videos using file size and duration comparison.

**Features:**
- Compares file size and duration
- Configurable tolerance
- Groups similar videos
- Moves duplicates to `Duplicates/` subdirectory

**Usage:**
```bash
python3 findDuplicateVideos.py --source ~/Videos --dry-run
```

#### recoveryCommon.py - Shared Utilities

Shared constants and helper functions for the recovery pipeline.

**File Type Detection:**
```python
from recoveryCommon import isImage, isVideo, IMAGE_EXTS, VIDEO_EXTS

# Supported formats
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".heic", ".cr2", ".nef"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".mpg", ".mpeg", ".mts", ".m2ts", ".wmv", ".3gp"}

# Check file types
if isImage(filePath):
    # Handle image
    pass

if isVideo(filePath):
    # Handle video
    pass
```

**Path Utilities:**
```python
from recoveryCommon import isRelativeTo

# Python 3.8-compatible relative path checking
if isRelativeTo(filePath, parentDir):
    # File is within parent directory
    pass
```

#### recoveryPipeline.py - Pipeline Orchestration

Main script that orchestrates the full recovery workflow.

**Usage:**
```bash
# Run full pipeline
python3 recoveryPipeline.py --source ~/recovered_photos

# With custom options
python3 recoveryPipeline.py --source ~/recovered_photos --dry-run

# Skip certain steps
python3 recoveryPipeline.py --source ~/recovered_photos --skip-dedup
```

**Dependencies:**
```bash
cd recoveryTools
pip install -r requirements.txt
# Installs: Pillow>=9.0.0, imagehash>=4.3.1, numpy>=1.20.0, ffmpeg-python>=0.2.0
```

### kohyaTools - Image Processing & AI Training

Tools for AI model training workflows, image processing, and ComfyUI integration.

#### kohyaConfig.py - Configuration Management

Shared configuration system used across multiple projects.

**File Location:** `~/.config/kohya/kohyaConfig.json`

**Structure:**
```json
{
  "sidecarEditor": {
    "inputRoot": "/path/to/images",
    "outputRoot": "/path/to/outputs"
  },
  "photoRecovery": {
    "sourceDir": "/path/to/photos",
    "backupDir": "/path/to/backup"
  },
  "kohya": {
    "baseDir": "/path/to/kohya",
    "outputDir": "/path/to/outputs"
  }
}
```

**Usage:**
```python
from kohyaConfig import loadConfig, saveConfig, setLogger

# Set up logging (required)
import logging
logger = logging.getLogger(__name__)
setLogger(logger)

# Load config
config = loadConfig()
inputRoot = config.get("sidecarEditor", {}).get("inputRoot")

# Save config
config.setdefault("photoRecovery", {})["sourceDir"] = "/new/path"
saveConfig(config)
```

**API:**
```python
def setLogger(externalLogger: logging.Logger) -> None:
    """Inject a logger from the calling script."""
    pass

def loadConfig() -> dict:
    """Load configuration from standard location."""
    pass

def saveConfig(config: dict) -> None:
    """Save configuration to standard location."""
    pass

def getConfigPath() -> Path:
    """Get path to config file."""
    return Path.home() / ".config" / "kohya" / "kohyaConfig.json"
```

**Logging Conventions:**
- Use injected logger via `setLogger()`
- Prefix dry-run operations with `"...[]"`
- Regular operations with `"..."`
- Use lowercase for messages

#### Other kohyaTools Scripts

**createKohyaDirs.py**: Set up directory structure for training
```bash
python3 createKohyaDirs.py --base-dir ~/kohya_projects
```

**trainKohya.py**: LoRA training orchestration
```bash
python3 trainKohya.py --config training_config.json
```

**img2ImgComfy.py**: Image-to-image processing via ComfyUI
```bash
python3 img2ImgComfy.py --input image.png --prompt "description"
```

**batchImg2ImgComfy.py**: Batch image processing
```bash
python3 batchImg2ImgComfy.py --input-dir ~/images --output-dir ~/outputs
```

**inspectLora.py**: Inspect LoRA model details
```bash
python3 inspectLora.py --model model.safetensors
```

### runpodTools - Cloud Environment Bootstrap

Modular, idempotent bootstrap system for RunPod cloud GPU instances. Sets up complete development environments for AI/ML work.

#### Key Features

- **Idempotent**: Steps check if work is done, skip if already complete
- **Modular**: Run individual steps, skip steps, or run from a checkpoint
- **State Tracking**: Tracks completed steps in `/workspace/runpodTools/state.env`
- **Smart Logging**: All output logged to timestamped files
- **Remote Orchestration**: Run from local machine via SSH

#### Directory Structure

```
runpodTools/
├── lib/                    # Reusable library functions
│   ├── common.sh           # Logging: log(), warn(), error(), die()
│   ├── ssh.sh              # SSH command builders
│   ├── apt.sh              # APT package management
│   ├── conda.sh            # Conda environment setup
│   ├── git.sh              # Idempotent git operations
│   ├── workspace.sh        # Paths and state tracking
│   └── diagnostics.sh      # System diagnostics
├── steps/                  # Bootstrap steps (run in order)
│   ├── 10_diagnostics.sh   # System diagnostics
│   ├── 20_base_tools.sh    # Base system tools
│   ├── 30_conda.sh         # Miniconda setup
│   ├── 40_comfyui.sh       # ComfyUI installation
│   ├── 50_kohya.sh         # Kohya SS setup
│   └── 60_upload_models.sh # Model upload instructions
├── runpodBootstrap.sh      # Remote-side step runner
└── README.md               # Comprehensive documentation
```

#### Usage Examples

**Basic Setup:**
```bash
# From local machine, bootstrap remote RunPod instance
./runpodTools/runpodBootstrap.sh ssh root@HOST -p PORT -i ~/.ssh/id_ed25519

# With Kohya SS
./runpodTools/runpodBootstrap.sh --kohya ssh root@HOST -p PORT -i ~/.ssh/id_ed25519

# Dry run (see what would happen)
./runpodTools/runpodBootstrap.sh --dry-run ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```

**Advanced Options:**
```bash
# List available steps
./runpodBootstrap.sh --list ssh root@HOST -p PORT -i KEY

# Run only specific step
./runpodBootstrap.sh --only 40_comfyui ssh root@HOST -p PORT -i KEY

# Start from specific step
./runpodBootstrap.sh --from 30_conda ssh root@HOST -p PORT -i KEY

# Skip a step
./runpodBootstrap.sh --skip 20_base_tools ssh root@HOST -p PORT -i KEY

# Force rerun (ignore state)
./runpodBootstrap.sh --force ssh root@HOST -p PORT -i KEY

# Copy scripts only, don't run
./runpodBootstrap.sh --no-run ssh root@HOST -p PORT -i KEY
```

**Direct Remote Execution:**
```bash
# Already on RunPod instance
bash /workspace/runpodTools/runpodBootstrap.sh

# With options
bash /workspace/runpodTools/runpodBootstrap.sh --kohya --force

# List steps
bash /workspace/runpodTools/runpodBootstrap.sh --list
```

#### State Management

State file location: `/workspace/runpodTools/state.env`

```bash
# Example state file
DONE_DIAGNOSTICS=1
DONE_BASE_TOOLS=1
DONE_CONDA=1
DONE_COMFYUI=1
```

**Reset state:**
```bash
rm /workspace/runpodTools/state.env
# Or use --force flag
```

#### Library Functions

**common.sh** - Core utilities:
```bash
source lib/common.sh

log "message"              # Info logging
warn "message"             # Warning
error "message"            # Error
die "message"              # Error and exit
timestamp                  # Get timestamp
run command                # Execute with dry-run support
```

**workspace.sh** - State tracking:
```bash
source lib/workspace.sh

isStepDone "STEP_NAME"     # Check if step completed
markStepDone "STEP_NAME"   # Mark step complete
ensureDir "/path"          # Create directory if needed
```

**git.sh** - Idempotent git:
```bash
source lib/git.sh

cloneOrUpdate "url" "/path"  # Clone or pull if exists
```

**ssh.sh** - SSH utilities:
```bash
source lib/ssh.sh

buildSSHCommand "host" "port" "keyfile"  # Build SSH command
```

#### Adding New Steps

1. Create `steps/XX_stepname.sh`:
```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

source "$LIB_DIR/common.sh"
source "$LIB_DIR/workspace.sh"

main() {
  log "step: stepname"
  
  if isStepDone "STEPNAME" && [[ "${FORCE:-0}" != "1" ]]; then
    log "already done"
    return 0
  fi
  
  # Do work here
  run apt-get install -y package
  run conda create -n env python=3.10
  
  markStepDone "STEPNAME"
  log "done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
```

2. Add to `ALL_STEPS` array in `runpodBootstrap.sh`
3. Test with `--only XX_stepname`

#### Troubleshooting

**Check logs:**
```bash
ls -lrt /workspace/runpodTools/logs/
tail -f /workspace/runpodTools/logs/bootstrap.LATEST.log
```

**Check state:**
```bash
cat /workspace/runpodTools/state.env
```

**Reset and retry:**
```bash
# Reset all
rm /workspace/runpodTools/state.env

# Or force rerun
./runpodBootstrap.sh --force ssh root@HOST -p PORT -i KEY
```

#### Best Practices for runpodTools

- **Always use `set -euo pipefail`** in step scripts
- **Check state first**: Use `isStepDone()` before doing work
- **Use `run` wrapper**: Supports dry-run mode
- **Idempotent operations**: Steps should be safe to run multiple times
- **Move conflicting files**: Don't delete, rename with timestamp
- **Log everything**: Use `log()`, `warn()`, `error()` functions
- **Test with --dry-run**: Always test before running on production pod

## Development Workflow

### Testing Bash Scripts

**Always test in safe environment first:**
```bash
# Create test directory
mkdir -p ~/test_migration
cp -r ~/sample_files ~/test_migration/

# Run script on test directory
cd ~/test_migration
bash /path/to/organiseHome.sh

# Verify results
ls -la ~/test_migration/
```

### Testing Python Scripts

```bash
# Create test data
mkdir -p ~/test_photos
cp sample_images/* ~/test_photos/

# Run with dry-run first
python3 removeBlackImages.py --source ~/test_photos --dry-run

# Run actual processing
python3 removeBlackImages.py --source ~/test_photos

# Verify results
ls ~/test_photos/BlackImages/
```

### Testing recoveryTools

```bash
# Test individual tools
cd recoveryTools

# Filter black images
python3 filterBlackImages.py --source ~/test_data --dry-run

# Deduplicate images
python3 dedupeImages.py --source ~/test_data --dry-run

# Full pipeline
python3 recoveryPipeline.py --source ~/test_data --dry-run
```

### Testing kohyaTools

```bash
# Test configuration
cd kohyaTools
python3 -c "from kohyaConfig import loadConfig; print(loadConfig())"

# Test directory creation
python3 createKohyaDirs.py --base-dir /tmp/test_kohya --dry-run

# Test other tools with --help
python3 inspectLora.py --help
```

### Testing runpodTools

```bash
# Dry run bootstrap
cd runpodTools
./runpodBootstrap.sh --dry-run --list

# Test library functions
bash -c "source lib/common.sh && log 'test message'"

# Test state tracking
bash -c "source lib/workspace.sh && isStepDone 'TEST' && echo 'done' || echo 'not done'"

# Test step independently
bash steps/10_diagnostics.sh
```

### Integration Testing

```bash
# Full pipeline test
mkdir -p ~/test_recovery
cp -r ~/sample_photos ~/test_recovery/

# Step 1: Remove black images
python3 removeBlackImages.py --source ~/test_recovery

# Step 2: Find duplicates
python3 findDuplicateImages.py --source ~/test_recovery

# Verify clean directory
ls ~/test_recovery/
```

## Common Tasks

### Adding New Recovery Tool

1. Create Python script following template:
```python
#!/usr/bin/env python3
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Tool description")
    parser.add_argument("--source", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    
    sourceDir = Path(args.source).expanduser().resolve()
    if not sourceDir.is_dir():
        raise SystemExit(f"Not a directory: {sourceDir}")
    
    processTool(sourceDir, args.dry_run)

def processTool(sourceDir, dryRun):
    """Implement tool logic."""
    filteredDir = sourceDir / "FilteredItems"
    if not dryRun:
        filteredDir.mkdir(exist_ok=True)
    
    # Process files
    for item in sourceDir.iterdir():
        if shouldFilter(item):
            target = filteredDir / item.name
            if dryRun:
                print(f"Would move: {item} -> {target}")
            else:
                item.rename(target)

if __name__ == "__main__":
    main()
```

2. Add tests
3. Update documentation
4. Test with real data (carefully!)

### Adding New Bash Script

1. Start with safety header:
```bash
#!/usr/bin/env bash
set -euo pipefail
```

2. Add helper functions
3. Implement main logic with clear progress messages
4. Test in isolated environment
5. Add to documentation

## Safety Guidelines

### Bash Scripts
- **Always** use `set -euo pipefail`
- Quote all variable expansions: `"$VAR"`
- Use `[[` for conditionals
- Check existence before operations
- Provide interactive confirmations for destructive actions
- Use `-i` flag for `mv` and `cp` commands

### Python Scripts
- Validate all path arguments with `Path.resolve()`
- Support `--dry-run` for testing
- Create filtered subdirectories, don't delete
- Log all operations
- Handle errors gracefully (don't crash on one bad file)
- Preserve original files when possible

## Troubleshooting

### Bash Script Issues

**Problem:** Script fails with "unbound variable"

**Solution:** Check all variables are set:
```bash
sourceDir="${1:-}"
if [ -z "$sourceDir" ]; then
    echo "Error: No source directory specified"
    exit 1
fi
```

**Problem:** Paths with spaces cause issues

**Solution:** Always quote variables:
```bash
mv "$sourceFile" "$targetDir/"  # Correct
mv $sourceFile $targetDir/      # Wrong!
```

### Python Script Issues

**Problem:** Path resolution fails

**Solution:** Use proper exception handling:
```python
try:
    sourceDir = Path(args.source).expanduser().resolve(strict=True)
except Exception as e:
    raise SystemExit(f"Invalid path: {e}")
```

**Problem:** Out of memory with large image collections

**Solution:** Process in batches:
```python
from itertools import islice

def process_in_batches(files, batch_size=100):
    iterator = iter(files)
    while batch := list(islice(iterator, batch_size)):
        for file in batch:
            process_file(file)
```

## When Contributing

### Pre-commit Checklist
- [ ] Bash scripts: `shellcheck` passes
- [ ] Python scripts: All tests pass
- [ ] Tested in safe/isolated environment
- [ ] Dry-run mode tested (where applicable)
- [ ] Documentation updated
- [ ] No hardcoded paths
- [ ] Error handling appropriate
- [ ] Progress messages clear
- [ ] For runpodTools: Steps are idempotent
- [ ] For recoveryTools: In-place processing pattern followed
- [ ] For kohyaTools: Configuration properly managed

### Code Review Focus
- **Safety first**: Destructive operations protected
- **Path handling**: Correct quotes and resolution
- **Error messages**: Helpful and actionable
- **Dry-run support**: Present where appropriate
- **In-place processing**: Subdirectories, not deletion (for recovery tools)
- **Idempotency**: Safe to run multiple times (for runpodTools)
- **State tracking**: Properly uses state file (for runpodTools)
- **Configuration**: Uses kohyaConfig.py correctly (for kohyaTools)

### Subproject-Specific Guidelines

#### recoveryTools
- Follow in-place processing pattern
- Move filtered items to subdirectories
- Support `--dry-run` flag
- Handle errors gracefully per file
- Use `recoveryCommon.py` for shared utilities
- Document supported file formats

#### kohyaTools
- Use `kohyaConfig.py` for configuration
- Inject logger with `setLogger()`
- Follow logging conventions (`...` prefix)
- Support dry-run with `...[]` prefix
- Integrate with ComfyUI where applicable

#### runpodTools
- Make all steps idempotent
- Use state tracking (`isStepDone`, `markStepDone`)
- Source library functions from `lib/`
- Use `run` wrapper for dry-run support
- Log with `log()`, `warn()`, `error()` functions
- Test with `--dry-run` before production
- Document new steps in README.md

## Resources

### Bash
- ShellCheck: https://www.shellcheck.net/
- Bash Guide: https://mywiki.wooledge.org/BashGuide

### Python
- pathlib documentation: https://docs.python.org/3/library/pathlib.html
- argparse guide: https://docs.python.org/3/library/argparse.html
- imagehash: https://github.com/JohannesBuchner/imagehash

### System
- Ubuntu documentation: https://help.ubuntu.com/
- Pop!_OS documentation: https://support.system76.com/

---

**Note**: This project prioritizes safety and recoverability. Always test in isolated environments, use dry-run modes, and preserve original data by moving to subdirectories rather than deleting.
