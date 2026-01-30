# GitHub Copilot Instructions for linuxMigration

## Project Overview

linuxMigration is a collection of shell scripts and Python utilities for managing Linux system migration, file organization, and media recovery. It includes tools for organizing home directories, installing applications, processing recovered files, and managing gaming environments.

## Quick Start

### Prerequisites
- Linux OS (tested on Pop!_OS / Ubuntu)
- Bash shell
- Python 3.8 or higher
- Standard Linux utilities (mv, mkdir, etc.)

### Setup for Development
1. Clone the repository
2. For recovery tools, install dependencies:
   ```bash
   cd recoveryTools
   pip install -r requirements.txt
   ```
3. Make scripts executable:
   ```bash
   chmod +x *.sh
   ```

### Running Scripts
- Shell scripts: `./scriptName.sh` or `bash scriptName.sh`
- Python scripts: `python3 scriptName.py` (use `--help` for options)
- Recovery pipeline: `cd recoveryTools && python3 recoveryPipeline.py --source /path/to/images`

## Architecture & Key Components

### Directory Structure
- **Root level**: Main shell scripts for system management and organization
- **recoveryTools/**: Python utilities for media file recovery and deduplication
- **kohyaTools/**: Tools related to image processing workflows
- **runpodTools/**: Cloud computing environment setup utilities

### Core Technologies
- **Bash Scripting**: Primary automation and system management
- **Python**: Media processing, recovery tools, and utilities
- **Image Processing**: PIL/Pillow, imagehash for deduplication
- **Video Processing**: ffmpeg integration for video analysis

## Development Standards

### Code Style & Quality
- **Bash Scripts**: Use `set -euo pipefail` for safety, follow shellcheck recommendations
- **Python Code**: Follow PEP 8 conventions
- **Error Handling**: Always validate inputs and provide clear error messages
- **Documentation**: Include header comments explaining script purpose and usage

### Naming Conventions
- **Shell Scripts**: Use descriptive names with `.sh` extension (e.g., `organiseHome.sh`)
- **Python Scripts**: Use snake_case with `.py` extension (e.g., `dedupe_images.py`)
- **Functions**: camelCase for bash functions, snake_case for Python functions
- **Variables**: lowercase with underscores for multi-word names
- **Constants**: UPPERCASE_WITH_UNDERSCORES

### Script Organization
- Keep scripts focused on a single purpose
- Use helper functions for repeated operations
- Include usage information and help text
- Validate all required arguments and paths

## Bash Scripting Guidelines

### Safety Patterns
- Always use `set -euo pipefail` at the start of scripts
- Quote all variable expansions: `"$VAR"` not `$VAR`
- Use `[[` for conditionals instead of `[`
- Check if paths exist before operating on them

### Common Patterns
```bash
#!/usr/bin/env bash
set -euo pipefail

# Helper function example
make_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo "creating directory: $dir"
        mkdir -p "$dir"
    fi
}

# Safe file operation
move_if_exists() {
    local src="$1"
    local dest="$2"
    if [ -e "$src" ]; then
        mv -i "$src" "$dest/"
    fi
}
```

### User Interaction
- Provide clear progress messages
- Use `echo "=== Section Title ==="` for major operations
- Use `-i` flag for interactive confirmations on destructive operations
- Exit with appropriate status codes (0 for success, non-zero for errors)

## Python Recovery Tools Guidelines

### Recovery Pipeline Pattern
- Scripts should work in-place, preserving directory structure
- Create subdirectories for filtered items (e.g., `BlackImages/`, `Duplicates/`)
- Support `--source` argument for target directory
- Use `argparse` for command-line argument parsing
- Validate paths using `pathlib.Path` with `resolve()`

### Image/Video Processing
- Use PIL/Pillow for image operations
- Use `imagehash` for perceptual hashing and deduplication
- Support common formats: JPEG, PNG, MP4, MOV, etc.
- Handle errors gracefully (corrupted files, missing metadata)

### Common Patterns
```python
#!/usr/bin/env python3
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Tool description")
    parser.add_argument("--source", required=True, help="Source directory")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()
    
    try:
        source_dir = Path(args.source).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise SystemExit(f"Error resolving path: {e}")
    
    if not source_dir.is_dir():
        raise SystemExit(f"Directory does not exist: {source_dir}")
    
    # Process files...

if __name__ == "__main__":
    main()
```

### File Operations
- Use `Path.glob()` or `Path.rglob()` for file discovery
- Always check if files exist before operating on them
- Use `shutil.move()` for moving files between filesystems
- Preserve timestamps and permissions where appropriate

## Testing Requirements

### Test Structure
- Test scripts in a safe environment (use test directories)
- Verify file operations don't cause data loss
- Test with sample files before running on real data
- Use `--dry-run` flags where available

### Safety Checks
- Always backup important data before running migration scripts
- Test destructive operations with `-i` (interactive) flags first
- Verify paths are correct before bulk operations
- Use version control for configuration files

### Validation
- Check that files are moved, not deleted
- Verify directory structures are preserved
- Confirm file counts match expectations
- Test edge cases (empty directories, special characters in filenames)

## Security Considerations

### Path Handling
- Always validate and sanitize file paths
- Use absolute paths where possible
- Avoid operations on system directories without explicit confirmation
- Check permissions before attempting file operations

### User Data Protection
- Never delete files without explicit user consent
- Use move operations instead of delete where possible
- Create backup directories for filtered/removed items
- Log all file operations for audit trail

### Script Execution
- Require sudo only when necessary
- Validate that scripts are run with appropriate permissions
- Check for required tools/dependencies before execution
- Exit gracefully if prerequisites are not met

## File Organization Scripts

### Home Organization Pattern
Scripts like `organiseHome.sh` follow a consistent pattern:
1. Define helper functions (`make_dir`, `move_into_if_exists`)
2. Create top-level directory structure
3. Move items into appropriate categories
4. Provide feedback on each operation

### Categories
- **Apps**: Application-related directories
- **Cloud**: Cloud storage sync folders
- **Development**: Code repositories and dev tools
- **Games**: Gaming-related files and configs
- **Configs**: Configuration files and dotfiles
- **Archive**: Old/archived content

### Usage Guidelines
- Run scripts from the target directory or specify paths
- Review the script before running to understand what will be moved
- Use interactive mode (`-i` flag) when testing
- Keep original directory structure as backup initially

## Error Handling & Logging

### Bash Script Logging
- Echo clear status messages for each operation
- Use consistent formatting: `echo "=== Major Section ==="`
- Show what files/directories are being processed
- Exit with meaningful error messages on failure

### Python Script Logging
- Use `print()` for progress updates
- Include file paths in progress messages
- Report summary statistics (files processed, duplicates found, etc.)
- Log errors with context about what operation failed

### Error Messages
- Be specific about what went wrong
- Include the path or file that caused the error
- Suggest corrective actions when possible
- Exit with non-zero status codes on errors

### Example Patterns
```bash
# Bash
if [ ! -d "$target_dir" ]; then
    echo "Error: Directory does not exist: $target_dir"
    exit 1
fi

# Python
if not source_dir.is_dir():
    raise SystemExit(f"Error: Source directory does not exist: {source_dir}")
```

## Code Examples

### Bash Helper Functions
```bash
#!/usr/bin/env bash
set -euo pipefail

# Make directory if it doesn't exist
make_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo "creating directory: $dir"
        mkdir -p "$dir"
    else
        echo "directory already exists: $dir"
    fi
}

# Move file/directory if it exists
move_if_exists() {
    local src="$1"
    local dest="$2"
    if [ -e "$src" ]; then
        make_dir "$dest"
        echo "moving $src -> $dest"
        mv -i "$src" "$dest/"
    else
        echo "not found (skip): $src"
    fi
}
```

### Python Path Validation
```python
import argparse
from pathlib import Path

def validate_directory(path_str):
    """Validate and resolve a directory path."""
    try:
        path = Path(path_str).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise SystemExit(f"Error resolving path: {e}")
    
    if not path.is_dir():
        raise SystemExit(f"Directory does not exist: {path}")
    
    return path

# Usage
parser = argparse.ArgumentParser()
parser.add_argument("--source", required=True, help="Source directory")
args = parser.parse_args()
source_dir = validate_directory(args.source)
```

### Recovery Tool Pattern
```python
#!/usr/bin/env python3
"""
Tool description and purpose.
"""
import argparse
from pathlib import Path

def process_files(source_dir, dry_run=False):
    """Process files in the source directory."""
    for img_file in source_dir.rglob("*.jpg"):
        if dry_run:
            print(f"Would process: {img_file}")
        else:
            # Actual processing
            print(f"Processing: {img_file}")

def main():
    parser = argparse.ArgumentParser(description="Tool description")
    parser.add_argument("--source", required=True, help="Source directory")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without executing")
    args = parser.parse_args()
    
    source_dir = validate_directory(args.source)
    process_files(source_dir, args.dry_run)

if __name__ == "__main__":
    main()
```

## Common Patterns to Follow

1. **Safety First**: Always use `set -euo pipefail` in bash scripts, validate inputs
2. **Clear Feedback**: Provide progress messages for all operations
3. **Non-Destructive**: Move files to subdirectories instead of deleting
4. **Path Validation**: Resolve and check all paths before operations
5. **Error Handling**: Exit gracefully with meaningful error messages
6. **Dry Run Support**: Include `--dry-run` flags for testing operations
7. **Modularity**: Use helper functions for repeated operations
8. **Documentation**: Include usage information in script headers

## Repository-Specific Tools

### Recovery Tools (`recoveryTools/`)
- **dedupeImages.py**: Perceptual hash-based image deduplication
- **dedupeVideos.py**: Video file deduplication
- **filterBlackImages.py**: Remove corrupted/black images
- **recoveryPipeline.py**: Combined pipeline for image processing
- **sortImagesByResolution.py**: Organize images by resolution
- **sortVideosByDuration.py**: Organize videos by duration

### Organization Scripts
- **organiseHome.sh**: Structure home directory with standard categories
- **organiseOfficeFiles.sh**: Organize office documents
- **organiseWindowsHome.sh**: Windows home directory migration
- **pdfFiler.sh**: PDF organization and filing

### Installation Scripts
- **installLinuxApps.sh**: Install common Linux applications
- **setupBattlenetPrefix.sh**: Configure gaming environment

## When Contributing

- Test scripts in a safe environment before production use
- Preserve existing file organization patterns
- Include help text and usage examples
- Verify scripts work on both Ubuntu and Pop!_OS
- Check for required dependencies before execution
- Document any new tools or significant changes
- Use `--dry-run` for testing file operations
- Maintain backward compatibility with existing scripts
