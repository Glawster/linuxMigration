# Filing Direct Payments statements (fileDpStatements)

`fileDpStatements` files the Direct Payments bank statements downloaded by
hand from the Danske Bank website. It moves each one from `~/Downloads` into
the Direct Payments cabinet, one folder per year, named after the statement
date with the month at the end.

## Usage

Download the statements from the bank website, then:

```bash
fileDpStatements            # preview: show what would happen
fileDpStatements --confirm  # move the statements (or -y)
```

| Option | Meaning |
| --- | --- |
| `-y`, `--confirm` | Move the statements. Without it the command only previews. |
| `--source DIR` | Folder holding the downloads (default `~/Downloads`). |
| `--target DIR` | Bank Statements folder (default `~/Documents/myCabinets/Benefits/Bank Statements`). |
| `--version` | Show the repository version. |
| `-h`, `--help` | Show the help. |

## What it does

The bank saves every download as `Statement 950246 60153699.PDF`, with
` (1)`, ` (2)` and so on for later ones. For each such file in the source
folder:

1. Page 1 is read with `pdftotext`. A file that is not a statement for
   account 950246 60153699 is left alone.
2. The statement date is the date line under the branch address (for example
   `30 October 2026`); the end of the statement period is the fallback.
3. The file is moved to
   `<target>/<yyyy>/<yyyy-mm-dd> - Direct Payments - Statement - <Mon>.pdf`,
   creating the year folder when needed.

## Duplicates and conflicts

Nothing is deleted or overwritten.

- **Already filed.** When a file with identical content is already in that
  year's folder, under any name, the download is sent to the desktop Trash.
  Content is compared rather than names because some earlier statements were
  saved under their download date.
- **Name taken.** When a *different* file already has the target name, the
  download stays in the source folder and a warning is logged.

The command exits with status `1` when any download was left in place, so
they are not missed.

## Requirements and logs

- `pdftotext` (poppler-utils) and `gio` (libglib2.0-bin).
- `organiseMyProjects` for `logUtils.sh`. The command uses the active
  `python3`, then the `py312` Conda environment, so it runs from any folder;
  `LOG_UTILS` can point at a specific `logUtils.sh`.
- Logs go to `~/.local/state/fileDpStatements/`.

## Tests

`tests/test_fileDpStatements.py` runs the real script against temporary
folders with generated statement PDFs; only `gio` is replaced, so nothing
reaches the real Trash:

```bash
python3 -m pytest tests/test_fileDpStatements.py
```
