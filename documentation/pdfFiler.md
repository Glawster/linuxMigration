# Filing inbox PDFs (pdfFiler)

`pdfFiler.sh` files the PDFs in `~/Documents/myCabinets/Inbox` one at a time.
For each PDF it shows page 1, asks which cabinet folder and document type it
is, works out the document date and files it as:

```text
<folder>/<yyyy-mm-dd> - <folder name> - <type>.pdf
```

## Usage

```bash
pdfFiler.sh            # preview: the dialogs run, nothing moves
pdfFiler.sh --confirm  # file the PDFs (or -y)
```

| Option | Meaning |
| --- | --- |
| `-y`, `--confirm` | Move the files. Without it the command only previews. |
| `--root DIR` | Cabinets folder (default `~/Documents/myCabinets`). |
| `--inbox DIR` | Folder to file from (default `<root>/Inbox`). |
| `--version` | Show the repository version. |
| `-h`, `--help` | Show the help. |

## Filing a PDF

PDFs are offered oldest first, `.pdf` or `.PDF`. The list is taken once at
the start, so a PDF you decline is not offered again in the same run.

1. Page 1 opens in an image window (`feh`, or `eog`).
2. **Folder:** choose a folder inside the cabinets. A folder elsewhere is
   refused and the PDF stays in the inbox.
3. **Type:** choose the document type. *Keep Original Name* uses the PDF's own
   name instead of a type.
4. **Date:** see below.
5. **Proceed?** shows the new name. *No* leaves the PDF in the inbox and moves
   on to the next one.

Cancelling the folder, type or date dialog stops the run.

The name uses the folder's name, or its parent's when the folder is a year:
filing into `Bank Statements/2026` gives
`2026-10-30 - Bank Statements - Statement.pdf`.

## How the date is found

The date comes from page 1 of the PDF. When the PDF has no text layer,
`ocrmypdf` reads it, if it is installed. The candidates are tried in this
order, and each must be a real calendar date (31/02/2026 is rejected):

1. A line that is only a date, such as `30 October 2026` on bank statements.
2. A date after a label such as `Date:`, `Invoice date` or `Statement date`.
3. The first date with the month written out (`30 Oct 2026`, `1st Sept 2026`).
4. The first ISO date (`2026-10-30` or `2026/10/30`).
5. The first numeric date, read the UK way, day first (`30/10/2026`).

When page 1 has no date, the file name is tried (`2026-10-30`, `20261030` or
`30-10-2026`, with `-`, `_` or `.`). When that fails too, you are asked, and
asked again until the date is valid.

## Duplicates and conflicts

Nothing is overwritten or deleted.

- **Already filed:** when the chosen folder already holds a file with
  identical content, under any name, the PDF is sent to the desktop Trash.
- **Name taken:** when a *different* file already has the new name, an error
  is shown and the PDF stays in the inbox.

## Requirements and logs

- Required: `pdftotext` and `pdftoppm` (poppler-utils), `zenity` and `gio`
  (libglib2.0-bin).
- Optional: `ocrmypdf` for scanned PDFs, `feh` or `eog` for the preview, and
  `wmctrl` to place the preview window.
- `organiseMyProjects` for `logUtils.sh`, found through the active `python3`
  or the `py312` Conda environment (or `LOG_UTILS`).
- Logs go to `~/.local/state/pdfFiler/`.

## Tests

`tests/test_pdfFiler.py` runs the real script on generated PDFs in temporary
folders. zenity, the preview window and `gio` are replaced by test doubles,
so no dialogs appear and nothing reaches the real Trash.

```bash
python3 -m pytest tests/test_pdfFiler.py
```
