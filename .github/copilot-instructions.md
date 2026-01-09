# GitHub Copilot Instructions for organiseMyPhotos

## Project Overview

organiseMyPhotos is a Python desktop application for managing, organizing, and syncing iCloud Photos. It features a Tkinter-based GUI with modular architecture for photo/video organization, contact sheet generation, and secure iCloud synchronization.

## Quick Start

### Prerequisites
- Python 3.8 or higher
- Windows OS (for pywin32 dependency)
- linux support too
- pip package manager

### Setup for Development
1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r dev-requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

### Running Tests
```bash
python -m pytest
```

### Code Formatting and Linting
- Format code: `black .`
- Check GUI naming: `python tests/runLinter.py` from organiseMyPhotos root
- Pre-commit hooks will automatically run formatters and linters

## Architecture & Key Components

### Directory Structure

### Core Technologies
- **GUI Framework**: Tkinter with custom frame templates
- **Photo Processing**: PIL/Pillow, imagehash, piexif for EXIF handling
- **Video Processing**: moviepy for video thumbnails and metadata
- **Cloud Integration**: pyicloud for iCloud Photos API
- **Security**: cryptography.Fernet for credential encryption
- **Testing**: pytest with custom fixtures

## Development Standards

### Code Style & Quality
- **Formatting**: Use `black` for consistent code formatting
- **Linting**: Custom GUI naming linter enforces UI component naming conventions
- **Pre-commit hooks**: Automatic formatting and linting before commits

### Naming Conventions
- **GUI Components**: Follow specific patterns (e.g., `frmMain`, `btnSave`, `lblStatus`)
- **Classes**: PascalCase (e.g., `MainFrame`, `ContactSheetFrame`)
- **Functions and Variables**: camelCase (e.g., `scanCategories`, `loadExistingHashes`, `analyzeFolders`)
- **Constants**: UPPERCASE_WITH_UNDERSCORES (e.g., `WINDOW_WIDTH`, `PAD_X`)

### File Organization

## GUI Development Guidelines

### Framework Patterns (if needed)
- Use `pack()` layout manager consistently (avoid `grid()`)
- Implement consistent padding using `PAD_X`, `PAD_Y` constants
- Follow the frame template pattern for new UI components
- Use status frames for user feedback and progress indication

### Component Standards (if needed)
- **Buttons**: Use `ttk.Button` with consistent styling
- **Entry Fields**: `ttk.Entry` with validation where appropriate
- **Labels**: `ttk.Label` for consistent appearance
- **Frames**: `ttk.Frame` for layout organization

### User Experience
- Provide progress feedback for long-running operations
- Implement error handling with user-friendly messages
- Use tooltips for complex UI elements
- Maintain consistent window sizing and positioning

## Testing Requirements

### Test Structure
- Use pytest conventions (`test_*.py` files, `test_*` functions)
- Create focused, single-purpose test functions
- Use `tmp_path` fixture for temporary file testing
- Mock external dependencies (iCloud API, file system operations)

### Test Categories
- **Unit Tests**: Individual function testing
- **Integration Tests**: Component interaction testing
- **GUI Tests**: User interface behavior validation
- **File Operation Tests**: Safe file handling verification

### Coverage Expectations
- Core business logic: >90% coverage
- File operations: Comprehensive edge case testing
- Error handling: All error paths tested
- GUI components: Key interaction flows tested

## Security Considerations

### Credential Handling
- Never hardcode credentials or API keys
- Use encrypted storage for sensitive data
- Implement secure 2FA flows
- Clear credential caches when requested

### File Operations
- Validate file paths and extensions
- Use safe file naming with conflict resolution
- Implement proper error handling for file operations
- Respect user permissions and system limitations

## Photo/Media Processing Guidelines

### File Type Support
- **Photos**: JPEG, TIFF with EXIF metadata preservation. cr2, NEF, ARW with conversion to PNG
- **Videos**: MP4, MOV with metadata extraction
- **Thumbnails**: Consistent sizing and quality
- **Contact Sheets**: Grid layout with drag-and-drop support

### Metadata Handling
- Preserve EXIF data during file operations
- Extract timestamp information reliably
- Handle missing or corrupted metadata gracefully
- Support multiple date sources (EXIF, file creation, modified)

### Performance Considerations
- Use lazy loading for large photo collections
- Implement progress feedback for batch operations
- Cache thumbnails to improve UI responsiveness
- Handle memory efficiently for large media files

## Error Handling & Logging

### Logging Standards
- Use centralized logger from `logUtils.py`
- Include module name and operation context
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR)
- Store daily logs with timestamp format

### Logging Guidelines
- **Message Format**: All messages in lowercase
- **Major Actions**: `"doing something..."` - major action being taken
- **Action Completion**: `"...something done"` - above action completed
- **General Updates**: `"...message"` - general update, doing this, transitory information
- **Information Display**: `"...message: value"` - display some information
- **Error Messages**: ERROR messages should be in Sentence Case
- **Usage**:
  ```python
  from src.logUtils import logger
  logger.info("...message")
  ```

### Error Recovery
- Implement graceful degradation for non-critical failures
- Provide user-actionable error messages
- Offer retry mechanisms for transient failures
- Maintain application stability during errors

## Code Examples

### Dry Run
in argparse setup:
'''python
    parser.add_argument("--dry-run", dest="dryRun", action="store_true", help="print actions/command only")
'''
in use, set up once:
'''python
    prefix = "...[]" if dryRun else "..."
'''
in logging/print statements:
'''python
    logger.info(f"{prefix} moving {sourcePath} to {destPath}")
'''

### GUI Component Creation
```python
class MyFrame(ScanFrame):
    def __init__(self, parent):
        super().__init__(parent, title="My Frame", actionButtonText="Process")

    def createFrame(self):
        self.frmMain = ttk.Frame(self)
        self.frmMain.pack(padx=PAD_X, pady=PAD_Y, fill=tk.BOTH, expand=True)

        # Use consistent naming and layout
        self.lblStatus = ttk.Label(self.frmMain, text="Ready")
        self.lblStatus.pack(pady=PAD_Y)
```

### File Operation Pattern
```python
from src.renameMedia import incrementFilename, renameFile

def safeFileOperation(sourcePath, destPath):
    try:
        # Use conflict resolution
        safeDest = incrementFilename(destPath)
        renameFile(sourcePath, safeDest)
        logger.info(f"...moved {sourcePath} to {safeDest}")
        return safeDest
    except Exception as e:
        logger.error(f"Failed to move file: {e}")
        raise
```

### Test Pattern
```python
def test_file_operation(tmp_path):
    # Arrange
    sourceFile = tmp_path / "test.jpg"
    sourceFile.write_text("test content")

    # Act
    result = processFile(str(sourceFile))

    # Assert
    assert result.exists()
    assert result.name.startswith("processed_")
```

## Common Patterns to Follow

1. **Consistent Error Handling**: Always use try-catch with proper logging
2. **User Feedback**: Provide progress updates for long operations
3. **Resource Management**: Clean up temporary files and resources
4. **Modular Design**: Separate UI logic from business logic
5. **Configuration**: Use centralized settings from `globalVars.py`

## When Contributing

- Run tests with `python -m pytest` before submitting
- Ensure GUI naming linter passes: `python tests/runLinter.py`
- Format code with `black`
- Update documentation for new features
- Consider backward compatibility for file operations
- Test with various photo/video formats and edge cases
