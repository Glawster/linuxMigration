<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# Agent Instructions -- Master Development Guidelines (v2)

## Table of Contents

1. [Overview](#overview)\
2. [Architecture Principles](#architecture-principles)\
3. [Development Standards](#development-standards)\
   3.1 [User Interface File Organisation](#user-interface-file-organisation)\
4. [Project Structure Standard](#project-structure-standard)\
5. [CLI Design Standards](#cli-design-standards)\
6. [Environment & Dependency Policy](#environment--dependency-policy)\
7. [Patterns](#patterns)\
8. [User Config Pattern](#user-config-pattern)\
9. [Error Handling & Logging](#error-handling--logging)\
10. [Security Standards](#security-standards)\
11. [Testing Standards](#testing-standards)\
12. [Performance Guidelines](#performance-guidelines)\
13. [Refactoring Guidelines](#refactoring-guidelines)\
14. [Common Principles to Always Follow](#common-principles-to-always-follow)

## Overview

These are master development guidelines for all projects.

Read `documentation/requirementsManagement.md`.
Read `documentation/repositoryLayout.md` before adding or moving repository content.
Read `documentation/testingProcess.md` before planning or reviewing tests.
Read `documentation/howToRelease.md` before planning or reviewing releases.
Read `documentation/agentImplementationWorkflow.md` before implementing or modifying agent logic.

Project-specific details belong in:

.github/additional-instructions.md

This document defines universal rules.
If any other repository guidance contradicts this file, this file takes precedence and the conflicting guidance should be removed or aligned.

## Architecture Principles

1. Core logic must never depend on UI frameworks\
2. Business logic must be testable without GUI\
3. GUI layers orchestrate --- they do not implement business logic\
4. CLI tools must be fully scriptable and capable of running non-interactively\
5. File operations must be centralized and reusable\
6. Logging must be initialized at entry point\
7. Scripts must be safe-by-default\
8. Move files instead of deleting where possible\
9. Prefer explicit over implicit behavior\
10. Validate all paths before use

## Development Standards

### Code Quality

- Python formatted with black\
- Bash uses set -euo pipefail\
- Use type hints\
- Use docstrings for public functions/classes

### Markdown Document Structure

- Each Markdown document must contain exactly one H1 title (`#`).\
- Major sections must use H2 (`##`) headings.\
- Subsections must descend one level at a time (`###`, then `####`, etc.).\
- Do not promote subsection headings to H1 for visual emphasis; use wording,
  section ordering, or separators instead.

### Commenting & Code Documentation Process

- Treat comments as first-class code documentation, not optional decoration\
- Add intent-level comments through non-trivial logic so readers can follow the workflow without reverse-engineering it\
- Prefer comments that explain why a block exists, the expected flow, and important assumptions\
- Avoid obvious comments that restate syntax line-by-line\
- Keep comments current when code changes; stale comments are defects and must be updated in the same change\
- For generated or agent-edited code, include concise inline guidance at each major step of the implementation

### Separation of Concerns

- UI separate from business logic\
- Core logic has no framework dependencies\
- Utilities isolated in dedicated modules\
- Tests mirror source structure

### User Interface File Organisation

#### Goal

User interface source files should be easy to understand from the top-level
class alone.

The structure of a file should reveal the application architecture rather than
implementation details.

#### Single Responsibility

A UI file should primarily define a single view or a tightly related UI concern.

Avoid embedding unrelated widgets, dialogs, prototype data or styling within the
same file.

Instead, create reusable components.

Good:

views/
    tactic/
        tacticDetailView.py

widgets/
    pitchWidget.py

dialogs/
    roleProfileDialog.py

styles/
    tacticDetail.qss

Bad:

tacticDetailView.py
    PitchWidget
    DisplaySlot
    StyleSheet
    SampleData
    Four Tab Implementations

#### View Structure within the UI

A view should read like an outline of the interface.

Preferred structure

class MyView(QWidget):

    __init__()

    _createLayout()

    _createHeader()

    _createContent()

    _createFooter()

Implementation details should live in helper classes or separate widgets.

The first 100 lines of a view should describe the UI structure, not implement every control.

#### Custom Widgets

Any widget that could reasonably be reused elsewhere should live in
widgets/.

Examples

PitchWidget

PlayerCard

RoleCard

FormationView

InstructionPanel

Do not define reusable widgets inside another view.

#### Tab Organisation

Each significant tab should be its own QWidget subclass.

Avoid methods such as

_createOverviewTab()

_createAnalysisTab()

when the implementation exceeds approximately 50 lines.

Instead

OverviewTab

AnalysisTab

InstructionsTab

ShapeTab

#### Styling

Do not embed long stylesheets inside Python.

Use .qss files.

Short style fragments (<10 lines) are acceptable.

Application themes belong in dedicated style resources.

#### Sample Data

Prototype or demonstration data must never be embedded in production views.

Store prototype data under

prototype/

or

tests/data/

Views should receive models rather than construct them.

#### File Readability

The purpose of a source file should be understandable by reading:

- imports
- class names
- public methods

without reading implementation details.

If understanding requires scrolling through hundreds of lines of drawing code,
stylesheets or sample data, the file should be refactored.

#### Refactoring Rule

When modifying an existing file, consider whether the change introduces a new
responsibility.

If a file begins to contain multiple distinct concerns, prefer extracting new
classes rather than extending the existing file.

The preferred solution is decomposition rather than growth.

#### Architectural Preference

Prefer composition over accumulation.

When adding new functionality:

1. Reuse an existing component if it has the same responsibility.
2. Create a new component if the responsibility is different.
3. Extend a file only if the new code serves the file's existing purpose.

Avoid creating "God classes" that combine views, widgets, styling, sample data,
business logic and persistence.

### Code Organisation & Function Naming Pattern

- Group functions by domain or purpose.
- Use `##` section headers with short lowercase names.
- Module-level function names should use the `domainAction` pattern.
  - domain first, then action. Use camelCase.
  - examples:
    - `configLoad`
    - `configSave`
    - `messageExtract`
    - `messageParse`
    - `whatsappWaitForReady`
  - avoid reversing the pattern (e.g. `loadConfig`, `extractMessage`).
- Class methods, classmethods and staticmethods may use an action-only name
  because the enclosing class already supplies the domain. `Project.update()`
  is valid; `projectUpdate()` remains valid too. Module-level functions still
  require `domainAction`.
- Nested or local helper functions may use ordinary descriptive names such as
  `fail`, `empty` or `box`. Do not require `domainAction` for them.
- Keep functions alphabetically ordered within each section unless readability will be reduced or precedence order is needed.
- Keep public workflow near the top.
- Keep low-level utilities near the bottom.
- Private helpers must start with `_`.
- Private constants may use a leading underscore on UPPER_CASE names, for
  example `_MAX_RETRIES`.

#### Example

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

## Project Structure Standard

Before adding or moving repository content, read the repository layout
definition at `documentation/repositoryLayout.md`. That document is authoritative
for project-specific directory and file placement. This file remains
authoritative for universal development and safety rules.
Repository-specific layout exceptions belong in
`.github/additional-instructions.md`; they may refine the shared layout but may
not override universal safety or development rules in this file.

Choose the entry-point pattern according to what is being built:

- a reusable library module or package does not need `main.py` or any executable
  entry point;
- a packaged CLI uses a declared console-script entry point, normally targeting
  a `main()` function inside the package;
- a GUI or standalone application exposes its entry point from the project
  package, for example `python -m projectName` via `package/__main__.py`.

New OMP Python projects use a root-level package named after the project:

    projectName/
    ├── projectName/
    │   └── __init__.py
    ├── documentation/
    ├── project/
    ├── tests/
    ├── pyproject.toml
    ├── projectNameEnvironment.yml
    ├── README.md
    └── .github/
        └── additional-instructions.md

Do not introduce a generic `src/` directory or a root `main.py` in a newly
scaffolded OMP project. Existing projects that already use those layouts are
not automatically reorganised.

Rules:

- In a multi-project repository, treat each project directory as its own project root and use the nearest owning boundary for code, tests, documentation, planning records, scripts, dependencies and output\
- Reserve repository-level folders for shared concerns, repository tooling and cross-project integration; project-specific tests belong in that project's `tests/` folder\
- Reusable library modules and packages do not require `main.py` or an executable entry point\
- Packaged CLIs use declared console-script entry points, normally targeting a package-level `main()` function\
- GUI and standalone applications expose an entry point from the project package\
- The application entry point sets the application logging context with `setApplication()`\
- Application and domain Python modules belong inside the project package\
- Optional UI or Qt scaffolds belong inside the project package\
- Documentation rule: only `README.md` may be at the project root; all other documentation must live under `documentation/`, and documentation file names should use camelCase except for `README.md`\
- The README must include a near-top Documentation section that links to every living guide in the repo so it remains the canonical entry point for all docs\
- Any routine that produces output files must place them in an `output/` folder directly under the project root\
- Core/business logic must remain testable without the UI

### Shared Runtime Modules

The canonical runtime package is `organiseMyProjects`. Import logging and
related helpers from that package:

    from organiseMyProjects.logUtils import getLogger, setApplication

Do not add a second runtime package named `omp` inside the
`organiseMyProjects` repository. That name already refers to this project.

## CLI Design Standards

CLI interfaces should be consistent, discoverable and composable so that knowledge gained using one project naturally transfers to every other project.

### Command Structure

CLI applications should use subcommands to group related functionality.

Prefer:

    application object action [options]

Examples:

    git branch create
    docker image ls
    kubectl get pods

Project examples:

    eolas family create
    eolas member add
    eolas report generate

    sportVision match analyse
    sportVision camera calibrate

    wowAddonHelper zygor install

Avoid exposing large numbers of unrelated top-level options.

Commands perform actions.

Options modify the behaviour of commands.

Prefer grouping functionality using subcommands. Where an application exposes multiple domains of functionality, use the hierarchy:

application object action [options]

Simpler applications may use:

application action [options]

### Discoverability

Commands should be self-discovering.

Users should be be able to navigate the command hierarchy using `--help` at every level.

Examples:

    app --help
    app family --help
    app report --help

Related functionality should normally be implemented using `argparse` subparsers.

### Command Naming

Objects should be nouns.

Examples:

    family
    member
    report
    camera
    repository

Actions should be verbs.

Aliases may be provided for convenience, but a single canonical command should exist. British English spelling is preferred where applicable (for example `analyse` rather than `analyze`).

### Options

Options modify command behaviour.

Examples:

    --confirm
    --verbose
    --quiet
    --json

### Universal Options

--help
--version
--confirm
--verbose
--quiet

### Command Naming Verbs

create
list
show
edit
delete

import
export

scan
analyse
verify

generate

status

sync

update

start
stop
restart

enable
disable

### Required Behaviour

All CLI applications should:

- Use `argparse`
- Validate all input paths before use
- Provide clear `--help` output
- Exit with status code `0` on success and non-zero on failure
- Initialise logging from the application entry point
- Print a clear completion summary where appropriate
- Support `--confirm` for operations that modify data
- Default to safe (dry-run) behaviour where destructive operations are possible

## Environment & Dependency Policy

- Target Python 3.10+\
- Use `pyproject.toml` as the authoritative packaged-Python dependency definition\
- Use a project-specific camelCase Conda environment file and editable install\
- Do not make `requirements.txt` the primary dependency mechanism for new packaged projects\
- Do not auto-install dependencies at runtime\
- Fail fast if external tools are missing\
- Validate system requirements explicitly

### Python Environment Standard

- Use Conda as the preferred Python environment manager.
- Every Python application should provide an `environment.yml`.
- Declare package dependencies in `pyproject.toml`.
- Use the Conda environment to install the project in editable mode.
- Document Conda installation before `venv` alternatives.

## Patterns

### Logging Pattern (logUtils)

All projects must use centralized logging from `organiseMyProjects.logUtils`.
Do not include "..." manually in log messages. logUtils owns prefixes/suffixes.

#### Application context

Each project sets its application context once in the root entry point:

    <projectName>/main.py

Use the project folder name unless there is a deliberate reason to override it:

    from pathlib import Path
    from organiseMyProjects.logUtils import getLogger, setApplication

    thisApplication = Path(__file__).parent.name
    setApplication(thisApplication)

    logger = getLogger(includeConsole=False)

`setApplication(thisApplication)` stores the active application name and creates the default log directory:

    ~/.local/state/<thisApplication>/

After `setApplication()` has run, do not pass `name` or `logDir` to `getLogger()` for normal application logging. `logUtils` owns that context.

#### Helper modules

Helper modules must not import `thisApplication` from `main.py` and must not redefine it.

Use this pattern everywhere outside the entry point:

    from organiseMyProjects.logUtils import getLogger

    logger = getLogger()

This works because the entry point sets the application context before importing modules that call `getLogger()`.

#### Entry-point initialisation

Initialise the application context before importing modules that rely on logging. Re-initialise console/dry-run behaviour in `main()` after parsing arguments:

``` python
from pathlib import Path
from organiseMyProjects.logUtils import getLogger, line, runStart, setApplication

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

    runStart()
    logger.doing("starting")
    line()
    # work here
    line()
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

#### Section separators

Call `logUtils.runStart()` once after `setApplication()` and before the first
application header. It writes a blank line, `>` followed by 80 hyphens and `<`,
then another blank line, directly to stdout and today's application log file.
Subcommands must not repeat a marker already emitted by their dispatcher.
The Bash equivalent is `runStart` from `logUtils.sh`, called after
`setApplication` and before the script header. Sourcing the helper does not emit
a marker. Bash `line` provides the same 80-hyphen section separator as
Python `logUtils.line()`, also writing directly to stdout and the log file.

After the complete command header and immediately before any final summary,
call `logUtils.line()`. It writes exactly 80 hyphens and a newline directly to
stdout and today's application log file, without logging records or prefixes.
Initialise the application context with `setApplication()` first. Use the shared
helper instead of hand-built separator strings or `logger.info()` separators.
The public `line()` helper is an explicit exception to module-level domainAction
naming. Only entry points establish application context; helpers reuse it.

```python
from organiseMyProjects import logUtils

logUtils.setApplication("example")
logger = logUtils.getLogger(includeConsole=True)
logUtils.runStart()
logger.doing("starting")
logUtils.line()
# Perform the command's work and report details here.
logUtils.line()
logger.value("processed", count)
logger.done("finished")
```


`runLinter` checks conventional Python entry points (`main()`, functions calling
`setApplication()`, and inline `__main__` guards) that emit `logger.*` headers:

- `LOG-SEC-001`: missing `runStart()` before the first header log call.
- `LOG-SEC-002`: missing `line()` immediately after the contiguous header logs.
- `LOG-SEC-003`: missing `line()` before summary logs ending with `logger.done()`.

Direct calls and `logUtils.runStart()` / `logUtils.line()` are recognised.
Comments and strings do not count. Tests, ordinary helpers and dispatchers with
no header output are excluded. These are static convention checks: arbitrary
logger aliases, print-only headers, output delegated to helper functions, and
Bash scripts are not analysed for section placement.

#### Semantic log methods

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

#### The `action()` / dry-run guard pattern

``` python
logger.info("opening poll %s/%s: %s", index, totalPolls, pollTitle)
```

1. Use `logger.doing()` only for lifecycle steps with no embedded values.

``` python
logger.doing("attendance export")
logger.doing("scraping polls")
```

Avoid:

``` python
logger.doing(f"attendance export for {group}")
```

1. Use `logger.action()` for side effects (dry-run aware).

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

#### Info/Value Logging Rule

Use logger.info() for narrative messages with no variables, or formatted messages with two or more variables.
Use logger.value("name", value) for exactly one variable.
No other logger methods should receive variable arguments.

#### No fallback logging

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

#### `drawBox()` for prominent log entries

``` python
from organiseMyProjects.logUtils import drawBox

drawBox("Sync complete\n3 updated, 0 failed", logger=logger)
```

#### Bash Logging (logUtils.sh)

Bash scripts must source `logUtils.sh` from the `organiseMyProjects` package.

##### Sourcing and initialisation

``` bash
source "$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))')/logUtils.sh"
setApplication "myScript"
```

`setApplication "myScript"` writes logs to `~/.local/state/myScript/myScript-<date>.log`.

An optional base directory can be supplied:

``` bash
setApplication "myScript" "/tmp/logs"
```

##### Semantic log functions

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

##### The `log_action()` / dry-run guard pattern (bash)

``` bash
dryRun=1  # non-empty = dry-run; unset or empty = live

log_action "moving file: $src → $dest"
if [[ -z "${dryRun:-}" ]]; then
    mv "$src" "$dest"
fi
```

#### Dry-Run Pattern

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

#### Recovery Pipeline Pattern

- Never destroy original structure\
- Create subdirectories for filtered items\
- Support --source\
- Support --confirm\
- Always validate paths first

#### Stop File Pattern

- Check for stop file periodically\
- Exit gracefully if detected\
- Log cancellation event

## User Config Pattern

Applications store user-level defaults and preferences in:

```text
~/.config/<application>/config.json
```

Rules:

- Use JSON objects, not `key=value` files\
- Preserve existing and unknown keys when updating config\
- Use clear, stable key names such as `source`, `month`, or `groupName`\
- Validate config values before using them\
- Create the config directory only when writing config\
- Preference updates, such as saving a `--source` override, may be written even during dry-run\
- Dry-run guards apply to workflow side effects, not to preference persistence unless the user explicitly asks for config preview only

## Error Handling & Logging

- Fail fast for invalid input\
- Gracefully degrade for non-critical failures\
- Always log errors with context\
- Never swallow exceptions silently

## Security Standards

- Never hardcode credentials\
- Never log sensitive data\
- Validate and sanitize file paths\
- Respect user permissions

## Testing Standards

- Follow `documentation/testingProcess.md` as the authoritative testing process.\
- Name Python test modules `test_camelCaseName.py`; pytest discovery must use
  `python_files = test_[a-z]*.py`.\
- Core logic \>90% coverage\
- Critical functions 100% coverage\
- Use Arrange--Act--Assert\
- Use tmp_path for file tests

## Performance Guidelines

- Profile before optimizing\
- Use lazy loading for large sets\
- Cache expensive computations\
- Batch filesystem operations

## Refactoring Guidelines

Refactor when:

- Function \> 40 lines\
- Class \> 300 lines\
- Nesting \> 3 levels\
- Repeated logic appears twice

## Development Status and Documentation Ownership

Status has one owner. Requirements describe obligations, design documentation
describes behaviour, and Git records delivery history.
`project/currentIncrement.md` alone records transient implementation status.

When implementing or completing an increment, update
`project/currentIncrement.md` with the active increment, objective, scope,
acceptance work, verification still required and immediate next action. Replace
the previous increment's transient detail when the next increment starts; do
not turn the file into a running delivery history.

Do not propagate implementation-status statements into requirements, README
files, ADRs or design documentation unless the work changes the durable truth
that document is responsible for describing:

- requirements record durable obligations and acceptance criteria; supported
  lifecycle metadata such as `ToDo`, `InProgress` and `Completed` may remain;
- ADRs record architectural decisions and rationale;
- `documentation/` describes durable implemented behaviour and changes when
  that behaviour or design changes;
- `README.md` provides a stable introduction, capabilities and navigation, and
  changes for meaningful durable capability or release changes where useful;
- tests provide executable acceptance and regression evidence; and
- commits, pull requests, tags and releases record what was delivered and when.

For example, an algorithm behaviour change updates its durable design guide; a
requirement scope change updates the requirement; completing one increment and
starting another updates `project/currentIncrement.md` and relies on Git for
the delivery history.

## Common Principles to Always Follow

1. Separation of concerns\
2. Safe-by-default execution\
3. Clear user feedback\
4. Centralized logging\
5. Non-destructive file handling\
6. Explicit path validation\
7. Dry-run support\
8. Small, focused functions\
9. Test before refactor\
10. Consistency across frameworks

End of Master Development Guidelines
