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
14. [Common Principles to Always
    Follow](#common-principles-to-always-follow)

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

    projectName/
    ├── src/
    │   └── projectName/
    │       ├── __init__.py
    │       ├── main.py
    │       ├── core/
    │       ├── ui/
    │       ├── utils/
    │       └── patterns/
    ├── Qt/ui
    ├── tests/
    ├── requirements.txt
    ├── README.md
    └── .github/
        └── additional-copilot-instructions.md

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

All projects must use centralized logging.

**Module-level initialisation** (bare logger, no dryRun yet):

``` python
from organiseMyProjects.logUtils import getLogger
logger = getLogger("projectName")
```

**Re-initialise in `main()` with full parameters** (logDir, includeConsole, dryRun):

``` python
logger = getLogger("projectName", logDir=logDir, includeConsole=True, dryRun=dryRun)
```

**Semantic log methods:**

``` python
logger.doing("scanning files")           # → scanning files...
logger.done("scan complete")             # → ...scan complete
logger.info("found n items")             # → ...found n items
logger.value("source dir", path)         # → ...source dir: /path
logger.action("moving file: src → dest") # → ...[] moving file: src → dest  (when dryRun=True)
```

**The `action()` / dry-run guard pattern:**

``` python
# Preferred: use logger.action() for operations guarded by dryRun
logger.action(f"moving file: {src} → {dest}")
if not dryRun:
    shutil.move(src, dest)
```

**`drawBox()` for prominent log entries:**

``` python
from organiseMyProjects.logUtils import getLogger, drawBox
drawBox("Sync complete\n3 updated, 0 failed", logger=logger)
```

-   Initialize logging at module level with `getLogger("projectName")`\
-   Re-initialize in `main()` passing `logDir`, `includeConsole`, and `dryRun`\
-   Use `logger.doing()` / `logger.done()` to bracket major operations\
-   Use `logger.action()` for operations that are skipped in dry-run — never construct a manual `prefix = "[] "` string\
-   Use lowercase messages\
-   Use consistent message patterns

------------------------------------------------------------------------

## Dry-Run Pattern

Use --confirm (never --dry-run).

``` python
prefix = "[] " if dryRun else ""
```

The `prefix` string is only used for `print()` console output. For logging, use `logger.action()` instead (see Logging Pattern above).

Guard operations:

``` python
# For logging: use logger.action()
logger.action(f"moving file: {src} → {dest}")
if not dryRun:
    shutil.move(src, dest)

# For print() console output only:
print(f"{prefix}moving file: {src}")
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
