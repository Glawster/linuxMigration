<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# OMP linter

## Invocation

The installed `organiseMyProjects` package is the single source of truth for
linting. From any managed project, run:

```bash
runLinter
```

Pass a file or directory only when a narrower target is required. Managed
projects do not carry private copies of `runLinter.py` or
`guiNamingLinter.py`; updating the installed OMP package updates linter
behaviour for every project that uses it.

## Naming rules

Module-level functions use `domainAction` camelCase. Digits may be part of the
domain before the action boundary, so names such as `_mp4BoxIterate` and
`_mp4MvhdCreationRead` are valid. Class methods may use action-only camelCase.
Nested/local helpers remain exempt from the module-level `domainAction` rule.

External frameworks and protocols may dictate method names. Such names are
exempt only when dispatch depends on their exact spelling. Textual is currently
recognised explicitly: in files importing `textual`, `action_*` action handlers
and `on_*` event/message handlers are accepted. This includes methods such as
`action_policy_positive`, `action_sender_edit`, `on_button_pressed`,
`on_click`, and `on_input_changed`. Arbitrary snake_case project methods remain
invalid.

## Logging case exceptions

`logger.info` and `logger.warning` messages remain lowercase, and
`logger.error` messages remain sentence case. Approved product/proper-name
tokens may retain their spelling without weakening the rest of the message.
The centrally maintained approved set is:

- `DJI`
- `Firefox`
- `GoPro`
- `Grok`
- `MCM`
- `SQLite`
- `TVDB`
- `X.ai`

Mixed-case tokens outside that list are still reported. Additions therefore
require an explicit OMP change and regression test rather than silently
relaxing the casing rule.

## Migration from project-local linters

`manageProject update -y` removes obsolete `tests/runLinter.py` and
`tests/guiNamingLinter.py` only when they are recognised as unmodified
OMP-managed copies. Locally changed or ambiguous files are preserved and
reported for manual review. Re-running update is idempotent and does not
recreate the old copies.
