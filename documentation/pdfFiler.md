# Filing inbox PDFs (pdfFiler)

`pdfFiler` files the scanned PDFs in `~/Documents/myCabinets/Inbox`. For each
PDF it suggests the cabinet folder, name, type and date from what is already
filed, and files it after one confirmation:

```text
Finance/Aviva/AV2550339/2026-04-05 - Aviva, AV2550339 - Tax.pdf
  because: matched AV2550339; type from the words in the letter ("Tax")
```

It is a Python project in `pdfFiler/` ([ADR 011](../project/adr/011-pdfFilerPython.md)),
started with `pdfFiler.sh`. Requirement:
[005](../project/requirements/features/005-pdfFilerSuggestions.md).

## Usage

```bash
pdfFiler.sh                 # preview: dialogs run, nothing moves or is learned
pdfFiler.sh --confirm       # file the inbox (or -y)
pdfFiler.sh suggest PDF...  # print the suggestion for PDFs; changes nothing
pdfFiler.sh index show      # what pdfFiler has learned, and how long it took
pdfFiler.sh --help          # also: inbox --help, suggest --help, ...
```

With no command, `pdfFiler.sh` runs `inbox file`.

| Option | Meaning |
| --- | --- |
| `-y`, `--confirm` | Move the files (`inbox file`). Without it, nothing moves. |
| `--root DIR` | Cabinets folder (default `~/Documents/myCabinets`). |
| `--inbox DIR` | Folder to file from (default `<root>/Inbox`). |
| `--version` | Show the repository version. |

## Filing a PDF

PDFs are offered oldest first (`.pdf` or `.PDF`), each once per run. Page 1
opens in an image window beside the dialogs.

- **With a suggestion**, one dialog shows the new path, the reasons and the
  other likely folders:
  - **File** files it as shown.
  - **Change…** opens the folder, type and date dialogs. The folder dialog
    starts in the suggested folder, and the type list has the suggestion
    first.
  - **Skip** leaves the PDF in the inbox.
- **Without a suggestion**, the folder, type, date and *Proceed?* dialogs are
  shown, as in `1.4a6`.
- **A rule marked `auto`** files without any dialog, but only with
  `--confirm`.

Cancelling the folder, type or date dialog stops the run.

## How the suggestion is made

pdfFiler learns from the cabinet's **names**, never from the content of filed
PDFs ([ADR 012](../project/adr/012-learnFromNames.md)). The index is rebuilt
on every run, skipping `Inbox` and `Archive`, and takes well under a second.

Evidence, strongest first:

1. **A rule** in `~/.config/pdfFiler/config.json` whose text all appears in
   the PDF.
2. **An identifier.** A plan or account number such as `AV2550339` that names
   a folder, appears in filed names, or was learned from an earlier filing.
3. **A folder's name in the text**, written as in the folder name or in
   capitals ("Aviva", "MBNA"). When two folders share a name, the rest of
   each path decides: "insurance", "policy", "cover" or "premium" in the text
   point to `Insurance/MBNA` rather than `Finance/MBNA`. These names are
   ignored:
   - names that start with a lower-case letter;
   - common names such as "Receipts" or "Statements";
   - names used by three or more folders, such as people's names (Andy,
     Kathy).

The **label** is the one most used in the folder's names (`Aviva, AV2550339`).
Otherwise it is the folder's name, or its parent's for a year folder.

The **type** comes from words in the text, such as statement, tax, renewal,
policy schedule, certificate of insurance, P60, payslip, invoice or receipt.
It can be any standard or already-used type. The folder's own types settle a
tie. With no such words, the type is the folder's most used type.

## How the date is found

The text of pages 1 and 2 is read, with OCR when there is no text layer.
Dates later than today are never used: OCR misreads such as `23/02/2028` are
skipped. Dates inside longer references, such as `PDOEA02-20260524-…`, are
never read.

| Type | Date |
| --- | --- |
| `Tax` | The end of the UK tax year covered: "6 April 2025" or "2025/26" gives `2026-04-05`. |
| `Statement` | The end of the stated period, the date after "to", even when OCR splits or reorders the lines. |
| Others | A date alone on its line, then one after a label such as `Date:`, then the first written-month, ISO and UK (day-first) date. |

When the text has no date, the file name is tried. When that fails too, you
are asked, and asked again until the date is real and not in the future.
gscan2pdf names scans by the scan date, so the text is the better source.

## Rules

Rules go in `~/.config/pdfFiler/config.json`; see
`pdfFiler/config.example.json`:

```json
{
  "rules": [
    {
      "name": "Direct Payments bank statement",
      "match": ["Account number: 950246 60153699"],
      "folder": "Benefits/Bank Statements",
      "yearSubfolder": true,
      "label": "Direct Payments",
      "type": "Statement",
      "date": "standaloneLine",
      "fileName": "{date} - {label} - {type} - {Mon}.pdf",
      "auto": false
    }
  ]
}
```

| Key | Meaning |
| --- | --- |
| `match` | Text that must all appear; case and spacing are ignored. |
| `folder` | Relative to the cabinets folder. `yearSubfolder` adds `<yyyy>/`. |
| `date` | `default`, `standaloneLine`, `statementPeriodEnd` or `taxYearEnd`. |
| `fileName` | Template using `{date}`, `{label}`, `{type}`, `{Mon}` and `{year}`; defaults to `{date} - {label} - {type}.pdf`. |
| `auto` | File without dialogs when run with `--confirm`. |

This rule names statements exactly as `fileDpStatements` does, which remains
as a shortcut for them.

## Learned numbers

When a PDF is filed with `--confirm`, its reference numbers are saved against
the chosen folder in `~/.config/pdfFiler/learned.json`. So next year's letter
about the same policy matches strongly. A number is saved when:

- it is on the same line as "Policy Number", "Account number", "Plan",
  "Reference" and the like, but not on a line about the sender's own
  registration (such as an FCA firm reference); or
- it is a letter-and-digit number of ten or more characters that appears
  twice.

A number already saved for another folder is never overwritten. The conflict
is listed by `index show`. A preview saves nothing.

## Duplicates and conflicts

Nothing is overwritten or deleted.

- **Already filed:** a PDF whose content is already in the target folder,
  under any name, goes to the desktop Trash.
- **Name taken:** when a different file has the new name, the PDF stays in
  the inbox with an error.

## Requirements and logs

- Required: `pdftotext` and `pdftoppm` (poppler-utils), `zenity` and `gio`
  (libglib2.0-bin).
- Optional: `ocrmypdf` for scans without text, `feh` or `eog` for the preview,
  and `wmctrl` to place the preview window.
- Python with organiseMyProjects. `pdfFiler.sh` uses `PDF_FILER_PYTHON`, then
  the active `python3`, then the `py312` Conda environment. Use
  `pdfFiler/environment.yml` on a fresh machine.
- Logs go to `~/.local/state/pdfFiler/`.

## Tests

```bash
cd pdfFiler && python -m pytest     # in py312
```

The tests use generated PDFs read by the real `pdftotext`, on temporary
cabinets. There are golden examples modelled on the Aviva tax letter, the
MBNA renewal and the Aviva ISA statement (with fictional numbers), and on the
Direct Payments rule. The CLI tests run the real `pdfFiler.sh` with zenity,
the preview and `gio` replaced.
