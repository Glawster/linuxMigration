<!-- synced from Glawster/organiseMyProjects -- do not edit directly -->
# GitHub Copilot Instructions -- Master Development Guidelines (v2)

------------------------------------------------------------------------

# Table of Contents

1.  [Overview](#overview)\
2.  [Architecture Principles](#architecture-principles)\
3.  [Development Standards](#development-standards)\
4.  [Project Structure Standard](#project-structure-standard)\
5.  [CLI Design Standards](#cli-design-standards)\
6.  [Environment & Dependency Policy](#environment--dependency-policy)\
7.  [Framework Guidelines](#framework-guidelines)\
8.  [Patterns](#patterns)\
9.  [Error Handling & Logging](#error-handling--logging)\
10. [Security Standards](#security-standards)\
11. [Testing Standards](#testing-standards)\
12. [Performance Guidelines](#performance-guidelines)\
13. [Refactoring Guidelines](#refactoring-guidelines)\
14. [Common Principles to Always Follow](#common-principles-to-always-follow)

------------------------------------------------------------------------

# Overview

These are master development guidelines for all projects.

Project-specific details belong in:

.github/additional-copilot-instructions.md

This document defines universal rules.

------------------------------------------------------------------------

# Architecture Principles

1.  Core logic must never depend on UI frameworks\
2.  Business logic must be testable without GUI\
3.  GUI layers orchestrate --- they do not implement business logic\
4.  CLI tools must run non-interactively\
5.  File operations must be centralized and reusable\
6.  Logging must be initialized at entry point\
7.  Scripts must be safe-by-default\
8.  Move files instead of deleting where possible\
9.  Prefer explicit over implicit behavior\
10. Validate all paths before use

------------------------------------------------------------------------

# Development Standards

## Code Quality

-   Python formatted with black\
-   Bash uses set -euo pipefail\
-   Use type hints\
-   Use docstrings for public functions/classes

## Separation of Concerns

-   UI separate from business logic\
-   Core logic has no framework dependencies\
-   Utilities isolated in dedicated modules\
-   Tests mirror source structure

------------------------------------------------------------------------

# Project Structure Standard

All applications must have a root entry point:

    projectName/
    ├── main.py
    ├── tests/
    ├── requirements.txt
    ├── README.md
    └── .github/
        └── additional-copilot-instructions.md

Larger applications may also use `src/` and `ui/` folders:

    projectName/
    ├── main.py
    ├── src/
    │   └── projectName/
    │       ├── __init__.py
    │       ├── core/
    │       ├── utils/
    │       └── patterns/
    ├── ui/
    ├── Qt/ui
    ├── tests/
    ├── requirements.txt
    ├── README.md
    └── .github/
        └── additional-copilot-instructions.md

Rules:

-   `main.py` lives at the project root and is the application entry point\
-   `main.py` sets the application logging context with `setApplication()`\
-   `src/` is optional and should be used for larger apps, reusable core logic, or UI-based apps\
-   `ui/` is optional and should contain UI orchestration/assets where useful\
-   Core/business logic must remain testable without the UI

------------------------------------------------------------------------

# CLI Design Standards

All CLI tools must:

-   Use argparse\
-   Validate paths before processing\
-   Log start and completion\
-   Exit with 0 on success, non-zero on failure\
-   Support --confirm (safe-by-default)\
-   Provide clear help text\
-   Print a completion summary

### Required Pattern

``` python
parser.add_argument(
    "--confirm",
    dest="confirm",
    action="store_true",
    help="execute changes (default is dry-run)",
)
dryRun = not args.confirm
```

Command behaviour:

| Command | Behaviour |
| --- | --- |
| `python main.py` | dry-run / safe preview |
| `python main.py --confirm` | execute changes |

Never expose `--dry-run` as the CLI flag. Use `dryRun` only as the internal boolean.

------------------------------------------------------------------------

# Environment & Dependency Policy

-   Target Python 3.10+\
-   Use requirements.txt unless packaged\
-   Do not auto-install dependencies at runtime\
-   Fail fast if external tools are missing\
-   Validate system requirements explicitly

------------------------------------------------------------------------

# Patterns

## Logging Pattern (logUtils)

All projects must use centralized logging from `organiseMyProjects.logUtils`.

### Application context

Each project sets its application context once in the root entry point:

```text
<projectName>/main.py
```

Use the project folder name unless there is a deliberate reason to override it:

``` python
from pathlib import Path
from organiseMyProjects.logUtils import getLogger, setApplication

thisApplication = Path(__file__).parent.name
setApplication(thisApplication)

logger = getLogger(includeConsole=False)
```

`setApplication(thisApplication)` stores the active application name and creates the default log directory:

```text
~/.local/state/<thisApplication>/
```

After `setApplication()` has run, do not pass `name` or `logDir` to `getLogger()` for normal application logging. `logUtils` owns that context.

### Helper modules

Helper modules must not import `thisApplication` from `main.py` and must not redefine it.

Use this pattern everywhere outside the entry point:

``` python
from organiseMyProjects.logUtils import getLogger

logger = getLogger()
```

This works because the entry point sets the application context before importing modules that call `getLogger()`.

### Entry-point initialisation

Initialise the application context before importing modules that rely on logging. Re-initialise console/dry-run behaviour in `main()` after parsing arguments:

``` python
from pathlib import Path
from organiseMyProjects.logUtils import getLogger, setApplication

thisApplication = Path(__file__).parent.name
setApplication(thisApplication)
logger = getLogger(includeConsole=False)

# Import app modules after setApplication() when they call getLogger().
from ui.mainMenu import mainMenu


def buildParser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--confirm",
        dest="confirm",
        action="store_true",
        help="execute changes (default is dry-run)",
    )
    return parser


def main() -> None:
    global logger

    parser = buildParser()
    args = parser.parse_args()
    dryRun = not args.confirm

    _name = Path(__file__).stem
    logger = getLogger(includeConsole=True, dryRun=dryRun)

    logger.doing(_name)
    # work here
    logger.done(_name)
```

`_name = Path(__file__).stem` identifies the entry-point module for messages such as `logger.doing(_name)`. It is not the application identity.

### Required logging rules

-   Call `setApplication(thisApplication)` once in root `main.py`\
-   Call `setApplication()` before importing modules that call `getLogger()`\
-   Use `logger = getLogger()` in helper modules\
-   Do not import `thisApplication` into helper modules\
-   Do not pass `name` or `logDir` to `getLogger()` for normal application logging\
-   Let `logUtils` write logs under `~/.local/state/<thisApplication>/`\
-   Use `logger.doing()` / `logger.done()` to bracket major operations\
-   Use `logger.action()` for operations that are skipped in dry-run\
-   Use lowercase messages\
-   Use consistent message patterns\
-   Do not add stdlib logging fallbacks\
-   Do not call `logging.basicConfig()` in application modules\
-   Do not pass module names such as `"myProject.exporter"` to `getLogger()`\
-   Do not construct a manual dry-run prefix for logging

### Semantic log methods

``` python
logger.doing("scanning files")           # → scanning files...
logger.done("scan complete")             # → ...scan complete
logger.info("found n items")             # → ...found n items
logger.value("source dir", path)         # → ...source dir: /path
logger.action("moving file: src → dest") # → ...[] moving file: src → dest  (when dryRun=True)
```

### The `action()` / dry-run guard pattern

``` python
logger.action(f"moving file: {src} → {dest}")
if not dryRun:
    shutil.move(src, dest)
```
### What not to do

#### Do not do this:
``` python
logger.info("...writing file")
logger.info("would write file")
logger.info ("[] writing file")
``` 
#### Do not branch logging:
``` python
if dryRun:
    logger.info("would write file")
else:
    logger.info("writing file")
```
#### Correct Pattern
``` python
logger.action("write polls.csv: %s rows", count)

if not dryRun:
    writeCsv(...)
```

### No fallback logging

External dependencies must fail fast. Never silently replace `logUtils`:

``` python
# Do not do this
try:
    from organiseMyProjects.logUtils import getLogger
except Exception:
    import logging
```

Use this instead:

``` python
from organiseMyProjects.logUtils import getLogger
```

If `setApplication()` has not been called before `getLogger()` is used without an explicit name, the program must raise a `RuntimeError`. This is intentional.

### `drawBox()` for prominent log entries

``` python
from organiseMyProjects.logUtils import drawBox

drawBox("Sync complete\n3 updated, 0 failed", logger=logger)
```

------------------------------------------------------------------------

## Dry-Run Pattern

Use `--confirm` as the CLI flag. Never expose `--dry-run` as the user-facing flag.

``` python
parser.add_argument(
    "-y",
    "--confirm",
    dest="confirm",
    action="store_true",
    help="execute changes (default is dry-run)",
)
dryRun = not args.confirm
```

The `prefix` string is only used for `print()` console output. For logging, use `logger.action()` instead.

Guard operations:

``` python
# For logging: use logger.action()
logger.action(f"moving file: {src} → {dest}")
if not dryRun:
    shutil.move(src, dest)
```

------------------------------------------------------------------------

## Recovery Pipeline Pattern

-   Never destroy original structure\
-   Create subdirectories for filtered items\
-   Support --source\
-   Support --confirm\
-   Always validate paths first

------------------------------------------------------------------------

## Stop File Pattern

-   Check for stop file periodically\
-   Exit gracefully if detected\
-   Log cancellation event

------------------------------------------------------------------------

# Error Handling & Logging

-   Fail fast for invalid input\
-   Gracefully degrade for non-critical failures\
-   Always log errors with context\
-   Never swallow exceptions silently

------------------------------------------------------------------------

# Security Standards

-   Never hardcode credentials\
-   Never log sensitive data\
-   Validate and sanitize file paths\
-   Respect user permissions

------------------------------------------------------------------------

# Testing Standards

-   Core logic \>90% coverage\
-   Critical functions 100% coverage\
-   Use Arrange--Act--Assert\
-   Use tmp_path for file tests

------------------------------------------------------------------------

# Performance Guidelines

-   Profile before optimizing\
-   Use lazy loading for large sets\
-   Cache expensive computations\
-   Batch filesystem operations

------------------------------------------------------------------------

# Refactoring Guidelines

Refactor when:

-   Function \> 40 lines\
-   Class \> 300 lines\
-   Nesting \> 3 levels\
-   Repeated logic appears twice

------------------------------------------------------------------------

# Common Principles to Always Follow

1.  Separation of concerns\
2.  Safe-by-default execution\
3.  Clear user feedback\
4.  Centralized logging\
5.  Non-destructive file handling\
6.  Explicit path validation\
7.  Dry-run support\
8.  Small, focused functions\
9.  Test before refactor\
10. Consistency across frameworks

------------------------------------------------------------------------

End of Master Development Guidelines
