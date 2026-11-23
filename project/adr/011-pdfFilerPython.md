# 011: pdfFiler moves to a Python project

- Status: Accepted
- Date: 2026-11-23
- Requirements: [005](../requirements/features/005-pdfFilerSuggestions.md)

## Context

`pdfFiler.sh` (fixed in `1.4a6`) is a Bash script. Requirement 005 adds an
index of the cabinet, scoring, rules from JSON, per-type date strategies and
learned identifiers. In Bash these are hard to write and to test without the
dialogs, and the guidelines require core logic that does not depend on the
GUI. `suggestUnwatched` is the precedent for a Python project in this
repository.

## Decisions

1. **`pdfFiler/` is a Python project** with `src/pdfFiler/`, its own `tests/`,
   `pyproject.toml` and `environment.yml`, following `suggestUnwatched`. The
   `src/` layout stops the `pdfFiler/` folder at the repository root from
   shadowing the package.
2. **Core and GUI are separate modules.** Text, dates, the cabinet index,
   rules, learning, suggestions and filing never import the dialog or preview
   modules. `inbox file` is the only command that uses them.
3. **No extra environment to install.** The package needs only the standard
   library and organiseMyProjects, so it runs in the `py312` environment that
   `.envrc` already uses, from source through `PYTHONPATH`.
   `pdfFiler/environment.yml` records the dependencies for a fresh machine.
4. **`pdfFiler.sh` becomes the launcher** for `python -m pdfFiler`, so the
   command keeps its name and its `1.4a6` options (`--confirm`, `--root`,
   `--inbox`, `--version`). With no subcommand it runs `inbox file`.
5. **`fileDpStatements` stays** as a shortcut. The same filing is also
   expressed as a pdfFiler rule (`config.example.json`), and a test shows the
   rule and the script give the same name.

## Consequences

- `tests/test_pdfFiler.py` (Bash) is replaced by `pdfFiler/tests/`, run with
  `python -m pytest pdfFiler` in `py312`, and added to the release checks.
- The Bash implementation of `1.4a6` is retired; its behaviour and safety
  rules carry over and are tested in Python.
