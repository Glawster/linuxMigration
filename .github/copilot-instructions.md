# GitHub Copilot Instructions - Generic Development Guidelines

<!-- This file is synced from the master template in Glawster/organiseMyProjects -->

## Overview

These are generic development guidelines for Python projects supporting multiple frameworks and patterns. They establish consistent coding standards, naming conventions, and best practices that can be applied across projects.

**Note**: For project-specific information, architecture details, and custom workflows, see `additional-copilot-instructions.md` in the `.github` directory.

## Quick Reference by Technology

- **Tkinter Desktop Apps**: See [Tkinter Guidelines](#tkinter-gui-development)
- **Qt/PySide6 Apps**: See [Qt Guidelines](#qt-gui-development)
- **FastAPI/React Web Apps**: See [Web Application Guidelines](#web-application-development)
- **DaVinci Resolve Scripts**: See [Video Automation Guidelines](#video-automation)
- **Bash/System Scripts**: See [Bash Scripting Guidelines](#bash-scripting)

## Development Standards

### Code Style & Quality
- **Python Formatting**: Use `black` for consistent code formatting
- **Bash Scripts**: Use `set -euo pipefail` for safety, follow shellcheck recommendations
- **JavaScript/React**: Prettier (standard React/ESLint rules)
- **Linting**: 
  - Python: Custom GUI naming linter for Tkinter, PEP 8 for general code
  - Bash: shellcheck
  - JavaScript: ESLint
- **Pre-commit hooks**: Automatic formatting and linting before commits
- **Testing**: pytest for comprehensive test coverage
- **Type hints**: Use type annotations where appropriate
- **Documentation**: Docstrings for all public functions and classes

### File Organization
- **UI Code**: Separate GUI components from business logic
- **Business Logic**: Core functionality independent of UI (NO framework dependencies in core logic)
- **Utilities**: Shared helper functions in dedicated modules
- **Tests**: Mirror source structure in test directory
- **Configuration**: Centralize constants and settings

## Naming Conventions by Framework

### Tkinter Projects
- **GUI Components**: Prefix-based (e.g., `frmMain`, `btnSave`, `lblStatus`)
- **Classes**: PascalCase (e.g., `MainFrame`, `DataProcessor`)
- **Functions and Variables**: camelCase (e.g., `processData`, `loadConfig`)
- **Constants**: UPPERCASE_WITH_UNDERSCORES (e.g., `MAX_SIZE`)
- **Private Members**: Leading underscore (e.g., `_internalMethod`)
- **Files**: camelCase (e.g., `dataProcessor.py`)

### Qt/PySide6 Projects
- **Classes**: PascalCase (e.g., `MainWindow`, `DataProcessor`)
- **Functions and Variables**: snake_case (e.g., `process_data`, `load_config`)
- **Qt Signals**: camelCase (e.g., `imageSelected`, `dataSaved`)
- **Constants**: UPPERCASE_WITH_UNDERSCORES (e.g., `MAX_SIZE`)
- **Private Members**: Leading underscore (e.g., `_internal_method`)
- **Files**: camelCase (e.g., `dataProcessor.py`)

### DaVinci Resolve / Video Automation
- **Functions and Variables**: camelCase (e.g., `getResolve`, `timelineExists`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `VIDEO_EXTENSIONS`)
- **Classes**: PascalCase (e.g., `TestTimeline`)
- **Files**: camelCase (e.g., `organiseHomeVideo.py`)

### Bash Scripts
- **Shell Scripts**: Descriptive names with `.sh` extension (e.g., `organiseHome.sh`)
- **Functions**: camelCase (e.g., `makeDir`, `moveIfExists`)
- **Variables**: camelCase (e.g., `sourceDir`, `targetPath`)
- **Constants**: UPPERCASE_WITH_UNDERSCORES

### Web Applications (FastAPI/React)
- **Python Classes**: PascalCase (e.g., `MediaEditor`)
- **Python Functions/Variables**: camelCase (e.g., `processUpload`)
- **JavaScript/React Components**: PascalCase (e.g., `UploadButton`)
- **Constants**: UPPERCASE_WITH_UNDERSCORES (e.g., `MAX_UPLOAD_SIZE`)

## Tkinter GUI Development

### Framework Patterns
- Use `pack()` layout manager consistently (avoid `grid()` unless necessary)
- Implement consistent padding using constants (e.g., `PAD_X`, `PAD_Y`)
- Follow frame-based component organization
- Use status indicators for user feedback and progress
- Inherit from base frame classes for standard functionality

### Component Standards
- **Buttons**: `ttk.Button` with `btn` prefix
- **Entry Fields**: `ttk.Entry` with `ent` prefix
- **Labels**: `ttk.Label` with `lbl` prefix
- **Frames**: `ttk.Frame` with `frm` prefix
- **Listboxes**: `tk.Listbox` with `lst` prefix
- **Comboboxes**: `ttk.Combobox` with `cmb` prefix
- **Checkbuttons**: `ttk.Checkbutton` with `chk` prefix
- **Radiobuttons**: `ttk.Radiobutton` with `rad` prefix
- **Text Widgets**: `tk.Text` with `txt` prefix
- **Scrollbars**: `ttk.Scrollbar` with `scr` prefix
- **Canvas**: `tk.Canvas` with `can` prefix

### GUI Naming Linter

#### Naming Rules
Widgets must follow specific prefixes based on their type. See component standards above.

#### Function Formatting Rules
- Methods longer than 4 lines should have a blank line after the `def` statement
- Short methods (≤4 lines) do not require blank line

#### Usage
```bash
runLinter                    # Lint current directory
runLinter path/to/file.py    # Lint specific file
runLinter path/to/directory  # Lint directory
```

### Example Code
```python
import tkinter as tk
from tkinter import ttk

class MyFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self._createWidgets()
        
    def _createWidgets(self):
        self.frmMain = ttk.Frame(self)
        self.frmMain.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        self.lblStatus = ttk.Label(self.frmMain, text="Ready")
        self.lblStatus.pack(pady=5)
        
        self.btnAction = ttk.Button(
            self.frmMain, 
            text="Process", 
            command=self._onAction
        )
        self.btnAction.pack(pady=5)
    
    def _onAction(self):
        """Handle button click."""
        self.lblStatus.config(text="Processing...")
        # Do work
        self.lblStatus.config(text="Complete")
```

## Qt GUI Development

### Framework Patterns
- Use Qt layouts (QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter)
- Use signals and slots for component communication
- Inherit from appropriate Qt widget classes
- Keep UI code separate from business logic
- Follow Qt's Model-View patterns where appropriate

### Component Standards
- **Buttons**: `QPushButton` or `QToolButton`
- **Labels**: `QLabel` for text and images
- **Text Input**: `QLineEdit` (single line) or `QTextEdit`/`QPlainTextEdit` (multi-line)
- **Lists**: `QListWidget` or `QListView` with models
- **Combos**: `QComboBox` for dropdown selections
- **Checks**: `QCheckBox` for boolean options
- **Radio**: `QRadioButton` for single-choice options
- **Containers**: `QWidget`, `QFrame`, `QGroupBox`
- **Dialogs**: `QDialog`, `QMessageBox`, `QFileDialog`
- **Menus**: `QMenuBar`, `QMenu`, `QAction`

### Qt-Specific Patterns

#### Signals and Slots
- Define custom signals using `Signal` from `PySide6.QtCore`
- Connect signals to slots using `.connect()`
- Emit signals to notify components
- Disconnect signals when widgets are destroyed if needed

#### Widget Initialization
- Call `super().__init__()` in widget constructors
- Set up UI in a separate `_setup_ui()` method
- Initialize member variables before UI setup
- Connect signals after UI is created

#### Layout Management
- Always use layouts, never fixed positions
- Use spacers to control widget spacing
- Set size policies appropriately
- Use `setSizeConstraint()` for proper sizing

#### Resource Management
- Clean up resources in `closeEvent()` or destructors
- Disconnect signals when appropriate
- Close file handles and network connections

### Example Code
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    """Custom widget with signal example."""
    
    processing_complete = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        
    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        
        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        
        self.action_button = QPushButton("Process")
        self.action_button.clicked.connect(self._on_action)
        layout.addWidget(self.action_button)
    
    def _on_action(self):
        """Handle button click."""
        self.status_label.setText("Processing...")
        result = self._do_processing()
        self.status_label.setText("Complete")
        self.processing_complete.emit(result)
    
    def _do_processing(self) -> str:
        """Perform the actual processing."""
        return "result"
```

## Web Application Development

### Architecture (FastAPI + React)

#### Backend (FastAPI)
- Use FastAPI for all API endpoints
- Design RESTful endpoints
- Validate incoming requests (file type, size, format)
- Serve static/media files securely
- Return clear JSON error messages

#### Frontend (React)
- Use functional components and hooks
- Leverage UI libraries (Material UI, etc.)
- Store API URLs in environment files
- Handle loading, errors, and job statuses gracefully
- Provide responsive layouts

#### Backend Example
```python
from fastapi import FastAPI, UploadFile, File

app = FastAPI()

@app.post("/upload/")
async def uploadMedia(file: UploadFile = File(...)):
    # Validate file type/size
    # Store in upload directory
    # Return file id/path
    ...
```

#### Frontend Example
```javascript
import React, { useState } from "react";
import { Button } from "@mui/material";

function UploadButton() {
  const [file, setFile] = useState(null);

  const handleChange = (e) => setFile(e.target.files[0]);
  
  const handleUpload = async () => {
    if (!file) return;
    const formData = new FormData();
    formData.append("file", file);
    await fetch("/upload/", { method: "POST", body: formData });
  };

  return (
    <>
      <input type="file" onChange={handleChange} />
      <Button onClick={handleUpload}>Upload</Button>
    </>
  );
}
```

## Video Automation

### DaVinci Resolve Integration
- Never assume DaVinci Resolve APIs are available
- Use try/except blocks around all Resolve API calls
- Support both `DaVinciResolveScript` and `bmd` import methods
- Test API compatibility across different versions

### Common Patterns

#### Timeline Management
```python
# Check if timeline exists
if timelineExists(project, timelineName):
    timeline = getTimelineByName(project, timelineName)
else:
    timeline = createTimelineInFolder(project, mediaPool, folder, timelineName)

# Check if timeline is empty
if timelineIsEmpty(timeline):
    mediaPool.AppendToTimeline(clips)
```

#### Safe API Calls
```python
# Use safeCall for uncertain API methods
success, result = safeCall(project, "GetTimelineByName", timelineName)
if success and result:
    # Use result
    pass
```

### Stop File Mechanism
- Support graceful cancellation via stop files
- Check for stop files at appropriate intervals
- Support multiple stop file locations
- Use `stopIfRequested()` pattern

## Bash Scripting

### Safety Patterns
- Always use `set -euo pipefail` at the start
- Quote all variable expansions: `"$VAR"` not `$VAR`
- Use `[[` for conditionals instead of `[`
- Check if paths exist before operating on them

### Common Patterns
```bash
#!/usr/bin/env bash
set -euo pipefail

# Helper function
makeDir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo "creating directory: $dir"
        mkdir -p "$dir"
    fi
}

# Safe file operation
moveIfExists() {
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
- Use `-i` flag for interactive confirmations
- Exit with appropriate status codes (0 for success, non-zero for errors)

## Testing Requirements

### Test Structure
- Use pytest conventions (`test_*.py` files, `test_*` functions)
- Create focused, single-purpose test functions
- Use `tmp_path` fixture for temporary file/directory testing
- Mock external dependencies appropriately
- Organize tests to mirror source structure

### Fast Validation Commands

For projects with quick validation:
```bash
# Compile check (< 1 second)
find . -name "*.py" -exec python3 -m py_compile {} \;

# Test suite (< 1 second)
python3 -m unittest discover tests/ -v

# Headless verification (< 1 second)
python3 headless_test.py
```

### Test Categories
- **Unit Tests**: Individual functions/methods in isolation
- **Integration Tests**: Component interactions
- **End-to-End Tests**: Complete workflows
- **GUI Tests**: User interface behavior
- **Headless Tests**: Testing without display (for CI)

### Coverage Expectations
- Core business logic: >90% coverage
- Critical functions: 100% coverage
- Error handling: All error paths tested
- Edge cases: Comprehensive boundary testing
- Happy path and failure scenarios both covered

### Test Best Practices
- Use descriptive test function names
- Follow Arrange-Act-Assert pattern
- Use `tmp_path` for file operations (automatic cleanup)
- Mock external services and expensive operations
- Provide descriptive error messages in assertions
- Test both success and failure scenarios
- Keep tests independent and repeatable
- Use parametrize for testing multiple inputs

## Error Handling & Logging

### Logging Standards
- Use centralized logging configuration
- Include module name and operation context
- Log at appropriate levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Store logs with timestamp and rotation as appropriate

### Logging Guidelines
- **Message Format**: Keep messages lowercase and consistent
- **Major Actions**: `"doing something..."` - action being initiated
- **Action Completion**: `"...something done"` - action completed
- **General Updates**: `"...message"` - informational updates
- **Information Display**: `"...message: value"` - displaying data
- **Error Messages**: Use Sentence Case for ERROR level messages

### Usage Example
```python
from src.logUtils import logger

logger.info("...processing data")
logger.error("Failed to process: error details")
```

### Error Recovery
- Implement graceful degradation for non-critical failures
- Provide user-actionable error messages
- Offer clear guidance when operations fail
- Handle missing dependencies gracefully
- Validate input before processing
- Use try-except blocks appropriately
- Log errors with sufficient context
- Maintain application stability during errors

## Security Considerations

### Credential Handling
- Never hardcode credentials or API keys
- Use encrypted storage for sensitive data
- Implement secure authentication flows
- Clear credential caches when requested

### File Operations
- Validate file paths and extensions
- Use safe file naming with conflict resolution
- Implement proper error handling
- Respect user permissions and system limitations
- Always sanitize user-generated names
- Support both Windows and Unix path separators

### Path Handling
- Always validate and sanitize file paths
- Use absolute paths where possible
- Avoid operations on system directories without confirmation
- Check permissions before attempting operations

### User Data Protection
- Never delete files without explicit user consent
- Use move operations instead of delete where possible
- Create backup directories for filtered/removed items
- Log all file operations for audit trail

### API/Web Security
- Validate all user input
- Use secure storage for sensitive data
- Handle exceptions without leaking sensitive information
- Follow principle of least privilege
- Limit upload size and sanitize files

## Media Processing

### File Type Support
- **Photos**: JPEG, PNG, TIFF with EXIF metadata preservation
- **Videos**: MP4, MOV with metadata extraction
- **Thumbnails**: Consistent sizing and quality

### Metadata Handling
- Preserve EXIF data during file operations
- Extract timestamp information reliably
- Handle missing or corrupted metadata gracefully
- Support multiple date sources (EXIF, file creation, modified)

### Processing Tools
- Use PIL/Pillow for image operations
- Use `imagehash` for perceptual hashing and deduplication
- Use ffmpeg for video analysis
- Handle errors gracefully (corrupted files, missing metadata)

### Performance Considerations
- Use lazy loading for large collections
- Implement progress feedback for batch operations
- Cache results to improve responsiveness
- Handle memory efficiently for large files
- Profile before optimizing
- Batch operations when possible

## Recovery Pipeline Pattern

### Python Recovery Tools
- Scripts should work in-place, preserving directory structure
- Create subdirectories for filtered items (e.g., `BlackImages/`, `Duplicates/`)
- Support `--source` argument for target directory
- Use `argparse` for command-line argument parsing
- Validate paths using `pathlib.Path` with `resolve()`
- Support `--dry-run` flags for testing operations

### Example Pattern
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
        sourceDir = Path(args.source).expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as e:
        raise SystemExit(f"Error resolving path: {e}")
    
    if not sourceDir.is_dir():
        raise SystemExit(f"Directory does not exist: {sourceDir}")
    
    # Process files...

if __name__ == "__main__":
    main()
```

## Common Patterns to Follow

1. **Separation of Concerns**: Keep GUI, business logic, and data access separate
2. **Error Handling**: Use try-except blocks with proper logging
3. **User Feedback**: Provide clear status messages and progress indicators
4. **Resource Management**: Clean up resources properly
5. **Modular Design**: Create small, focused functions and classes
6. **Configuration Management**: Centralize settings and constants
7. **Testing**: Write tests for all new functionality
8. **Documentation**: Add docstrings to public functions and classes
9. **Type Hints**: Use type annotations for better code clarity
10. **DRY Principle**: Don't repeat yourself - extract common code
11. **Safety First**: Validate inputs, use safe patterns
12. **Clear Feedback**: Provide progress messages for all operations
13. **Non-Destructive**: Move files instead of deleting when possible
14. **Path Validation**: Resolve and check all paths before operations
15. **Dry Run Support**: Include `--dry-run` flags for testing

## Best Practices

### Code Quality
- Write self-documenting code with clear names
- Keep functions short and focused (single responsibility)
- Use meaningful variable and function names
- Comment only when necessary to explain "why", not "what"
- Follow language-specific style guidelines
- Use type hints for function signatures

### Performance
- Profile before optimizing
- Use appropriate data structures
- Avoid premature optimization
- Cache expensive computations when appropriate
- Use lazy loading for large datasets
- Batch operations when possible

### Maintainability
- Keep dependencies minimal and well-documented
- Write tests that document expected behavior
- Use version control effectively
- Document breaking changes
- Consider backward compatibility
- Maintain compatibility through wrapper functions when needed

---

**This master document contains generic guidelines applicable across all projects. For project-specific details, architecture, and custom workflows, always refer to `additional-copilot-instructions.md` in the `.github` directory of each repository.**
