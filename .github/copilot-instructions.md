<!-- synced from Glawster/organiseMyProjects -- do not edit directly -->
# GitHub Copilot Instructions -- Master Development Guidelines (v2)

# Table of Contents

1.  [Overview](#overview)\
2.  [Architecture Principles](#architecture-principles)\
3.  [Development Standards](#development-standards)\
4.  [Project Structure Standard](#project-structure-standard)\
5.  [CLI Design Standards](#cli-design-standards)\
6.  [Environment & Dependency Policy](#environment--dependency-policy)\
7.  [Patterns](#patterns)\
8.  [User Config Pattern](#user-config-pattern)\
9.  [Error Handling & Logging](#error-handling--logging)\
10. [Security Standards](#security-standards)\
11. [Testing Standards](#testing-standards)\
12. [Performance Guidelines](#performance-guidelines)\
13. [Refactoring Guidelines](#refactoring-guidelines)\
14. [Common Principles to Always Follow](#common-principles-to-always-follow)

# Overview

These are master development guidelines for all projects.

Project-specific details belong in:

.github/additional-copilot-instructions.md

This document defines universal rules.
If any other repository guidance contradicts this file, this file takes precedence and the conflicting guidance should be removed or aligned.

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

## Code Organisation & Function Naming Pattern

- Group functions by domain or purpose.
- Use `##` section headers with short lowercase names.
- Function names should use the `domainAction` pattern.
    - domain first, then action. Use camelCase.
    - examples:
        - `configLoad`
        - `configSave`
        - `messageExtract`
        - `messageParse`
        - `whatsappWaitForReady`
    - avoid reversing the pattern (e.g. `loadConfig`, `extractMessage`).
- Keep functions alphabetically ordered within each section unless readability will be reduced or precedence order is needed.
- Keep public workflow near the top.
- Keep low-level utilities near the bottom.
- Private helpers must start with `_`.

### Example

class Example:

    ## config

    def configLoad(self):
        pass

    def configSave(self):
        pass

    ## message

    def messageExtract(self):
        pass

    def messageParse(self):
        pass

    ## utilities

    def _parseDate(self):
        pass

# Project Structure Standard

All applications must have a root entry point:

    projectName/
    ├── main.py
    ├── tests/
    ├── requirements.txt
    ├── README.md
    └── .github/
        └── additional-copilot-instructions.md

Larger applications may also use `src/`, `ui/`, and `qt/` folders:

    projectName/
    ├── main.py
    ├── src/
    │   └── projectName/
    │       ├── __init__.py
    │       ├── core/
    │       ├── utils/
    │       └── patterns/
    ├── ui/
    ├── qt/
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
-   Documentation rule: only `README.md` may be at the project root; all other documentation must live under `documentation/`, and documentation file names should use camelCase except for `README.md`\
-   The README must include a near-top Documentation section that links to every living guide in the repo so it remains the canonical entry point for all docs\
-   Any routine that produces output files must place them in an `output/` folder directly under the project root\
-   Core/business logic must remain testable without the UI

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
    "-y",
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

# Environment & Dependency Policy

-   Target Python 3.10+\
-   Use requirements.txt unless packaged\
-   Do not auto-install dependencies at runtime\
-   Fail fast if external tools are missing\
-   Validate system requirements explicitly

# Patterns

## Logging Pattern (logUtils)

All projects must use centralized logging from `organiseMyProjects.logUtils`.
Do not include "..." manually in log messages. logUtils owns prefixes/suffixes.

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
        "-y",
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

    logger = getLogger(includeConsole=True, dryRun=dryRun)

    logger.doing("starting")
    # work here
    logger.done("finished")
```

Use this in helper modules (do not use `setApplication()` in helper modules):

``` python
from organiseMyProjects.logUtils import getLogger

logger = getLogger()
```

`setApplication(thisApplication)` defines the active application and default log directory:

```text
~/.local/state/<thisApplication>/
```

After context is set, do not pass `name` or `logDir` for normal app logging.

### Semantic log methods

1. Use `logger.value()` for single values.

``` python
logger.value("group", config.groupName)
logger.value("month", config.monthWindow.monthKey)
logger.value("dryRun", config.dryRun)
```

Output Examples:

``` python
logger.doing("scanning files")           # → scanning files...
logger.done("scan complete")             # → ...scan complete
logger.info("found n items")             # → ...found n items
logger.value("source dir", path)         # → ...source dir: /path
logger.action("moving file: src → dest") # → ...[] moving file: src → dest  (when dryRun=True)
```

### The `action()` / dry-run guard pattern

``` python
logger.info("opening poll %s/%s: %s", index, totalPolls, pollTitle)
```

3. Use `logger.doing()` only for lifecycle steps with no embedded values.

``` python
logger.doing("attendance export")
logger.doing("scraping polls")
```

Avoid:

``` python
logger.doing(f"attendance export for {group}")
```

4. Use `logger.action()` for side effects (dry-run aware).

``` python
logger.action("write polls.csv rows: %s", count)
```

Use `logger.action()` with the write guard. Call `logger.done()` only if the action succeeds:

``` python
logger.action("moving file")
if not dryRun:
    shutil.move(src, dest)
    logger.done("moving file")
```

Do not manually build dry-run prefixes or branch log wording by `dryRun`.

### Info/Value Logging Rule

Use logger.info() for narrative messages with no variables, or formatted messages with two or more variables.
Use logger.value("name", value) for exactly one variable.
No other logger methods should receive variable arguments.

### No fallback logging

External dependencies must fail fast. Never silently replace `logUtils`:

``` python
# Do not do this
try:
    from organiseMyProjects.logUtils import getLogger, setApplication
except Exception:
    import logging
```

Use this instead:

``` python
from organiseMyProjects.logUtils import getLogger
```

If `setApplication()` has not been called before `getLogger()` is used without an explicit name, the program must raise a `RuntimeError`. This is intentional.

Do not call `logging.basicConfig()` in application modules.

### `drawBox()` for prominent log entries

``` python
from organiseMyProjects.logUtils import drawBox

drawBox("Sync complete\n3 updated, 0 failed", logger=logger)
```

### Bash Logging (logUtils.sh)

Bash scripts must source `logUtils.sh` from the `organiseMyProjects` package.

#### Sourcing and initialisation

``` bash
source "$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))')/logUtils.sh"
setApplication "myScript"
```

`setApplication "myScript"` writes logs to `~/.local/state/myScript/myScript-<date>.log`.

An optional base directory can be supplied:

``` bash
setApplication "myScript" "/tmp/logs"
```

#### Semantic log functions

``` bash
log_doing "scanning files"           #  →  scanning files...
log_done  "scan complete"            #  →  ...scan complete
log_info  "found 5 items"            #  →  ...found 5 items
log_value "source dir" "/home/andy"  #  →  ...source dir: /home/andy
log_action "moving file: a → b"      #  →  ...[] moving file: a → b  (when dryRun is non-empty)
                                     #  →  ...moving file: a → b     (when dryRun is unset/empty)
log_warn  "file not found"           #  →  WARNING: file not found
log_error "fatal problem"            #  →  ERROR: fatal problem  (stderr)
```

#### The `log_action()` / dry-run guard pattern (bash)

``` bash
dryRun=1  # non-empty = dry-run; unset or empty = live

log_action "moving file: $src → $dest"
if [[ -z "${dryRun:-}" ]]; then
    mv "$src" "$dest"
fi
```

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

## Recovery Pipeline Pattern

-   Never destroy original structure\
-   Create subdirectories for filtered items\
-   Support --source\
-   Support --confirm\
-   Always validate paths first

## Stop File Pattern

-   Check for stop file periodically\
-   Exit gracefully if detected\
-   Log cancellation event

# User Config Pattern

Applications store user-level defaults and preferences in:

```text
~/.config/<application>/config.json
```

Rules:

-   Use JSON objects, not `key=value` files\
-   Preserve existing and unknown keys when updating config\
-   Use clear, stable key names such as `source`, `month`, or `groupName`\
-   Validate config values before using them\
-   Create the config directory only when writing config\
-   Preference updates, such as saving a `--source` override, may be written even during dry-run\
-   Dry-run guards apply to workflow side effects, not to preference persistence unless the user explicitly asks for config preview only

# Error Handling & Logging

-   Fail fast for invalid input\
-   Gracefully degrade for non-critical failures\
-   Always log errors with context\
-   Never swallow exceptions silently

# Security Standards

-   Never hardcode credentials\
-   Never log sensitive data\
-   Validate and sanitize file paths\
-   Respect user permissions

# Testing Standards

-   Core logic \>90% coverage\
-   Critical functions 100% coverage\
-   Use Arrange--Act--Assert\
-   Use tmp_path for file tests

# Performance Guidelines

-   Profile before optimizing\
-   Use lazy loading for large sets\
-   Cache expensive computations\
-   Batch filesystem operations

# Refactoring Guidelines

Refactor when:

-   Function \> 40 lines\
-   Class \> 300 lines\
-   Nesting \> 3 levels\
-   Repeated logic appears twice

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

End of Master Development Guidelines
