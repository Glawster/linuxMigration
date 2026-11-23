# Filing inbox PDFs (pdfFiler)

`pdfFiler` files the scanned PDFs in `~/Documents/myCabinets/Inbox`. For each
PDF it suggests the cabinet folder, name, type and date from what is already
filed, and shows them in one filing window, ready to file:

```text
Finance/Aviva/AV2550339/2026-04-05 - Aviva, AV2550339 - Tax.pdf
  because: matched AV2550339; type from the words in the letter ("Tax")
```

It is a Python project in `pdfFiler/` ([ADR 011](../project/adr/011-pdfFilerPython.md)),
started with `pdfFiler.sh`. Requirement:
[005](../project/requirements/features/005-pdfFilerSuggestions.md).

## Usage

```bash
pdfFiler.sh                 # file the inbox (File moves, Skip leaves it)
pdfFiler.sh --confirm       # the same; --confirm is the default (or -y)
pdfFiler.sh suggest PDF...  # print the suggestion for PDFs; changes nothing
pdfFiler.sh index show      # what pdfFiler has learned, and how long it took
pdfFiler.sh --help          # also: inbox --help, suggest --help, ...
scanToInbox.sh              # duplex-scan into the Inbox with NAPS2
```

With no command, `pdfFiler.sh` runs `inbox file` and moves files. **Skip**
leaves a PDF in the inbox. **Stop** ends the run.

| Option | Meaning |
| --- | --- |
| `-y`, `--confirm` | Move the files. This is the default; the flag is accepted so existing commands keep working. |
| `--root DIR` | Cabinets folder (default `~/Documents/myCabinets`). |
| `--inbox DIR` | Folder to file from (default `<root>/Inbox`). |
| `--version` | Show the repository version. |

## Scanning into the Inbox

`scanToInbox.sh` loads the ScanSnap, scans, and writes one PDF into the
Inbox. NAPS2 talks to the scanner through SANE. The S1300i uses the
`epjitsu` backend, and the default device name `ScanSnap` matches it.

```bash
scanToInbox.sh                 # duplex, grayscale, 300 dpi, English OCR
scanToInbox.sh --front         # one side
scanToInbox.sh --color         # colour
scanToInbox.sh --list          # show the SANE devices
scanToInbox.sh --profile NAME  # a saved NAPS2 profile, still saved to the Inbox
```

| Option | Meaning |
| --- | --- |
| `--inbox DIR` | Where the PDF is written (default `~/Documents/myCabinets/Inbox`). |
| `--device NAME` | Partial scanner name (default `ScanSnap`). |
| `--front` | One-sided scan. |
| `--color` | Colour instead of grayscale. |
| `--profile NAME` | Saved NAPS2 profile. Use one when blank duplex backs should be dropped. The NAPS2 command line cannot exclude blank pages; a profile can. |
| `--list` | List SANE devices and exit. |

The file is named `YYYY-MM-DD-HHMMSS.pdf`. pdfFiler reads the document date
from the text, so this name is only a fallback. Install the NAPS2 deb.
The Flatpak build does not see extra SANE drivers. `naps2` must be on `PATH`.

## Filing a PDF

PDFs are offered oldest first (`.pdf` or `.PDF`), each once per run, in one
filing window ([ADR 013](../project/adr/013-filingWindow.md)):

- **Left:** page 1 of the PDF, drawn by Qt. ◀ ▶ change page, and **Fit
  width** / **Fit page** switch the zoom.
- **Right:** the fields, already filled in from the suggestion:
  - **Folder:** the list holds the suggestion and the other likely folders;
    **Browse…** picks any folder inside the cabinets.
  - **Type**, **Date** and **Label**.

  Choosing another folder recalculates the label, type and date you have not
  typed into.
- **File as** shows the whole new name on one line, and updates as you
  type. Problems appear beneath it in red and disable **File**: no folder, a
  bad or future date, or a name already taken. When the folder already holds
  this scan, **File** becomes **Trash duplicate**.
- **Why suggested** gives the reasons, such as "matched AV2550339".
- **Buttons:**
  - **File** (Enter) files it as shown.
  - **Skip** (Esc) leaves it in the inbox.
  - **Stop**, or closing the window, ends the run.

With no suggestion, the same window opens with the folder empty. **A rule
marked `auto`** files without the window.

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
| `auto` | File without the window. |

This rule names statements exactly as `fileDpStatements` does, which remains
as a shortcut for them.

## Learned numbers

When a PDF is filed, its reference numbers are saved against the chosen
folder in `~/.config/pdfFiler/learned.json`. So next year's letter about the
same policy matches strongly. A number is saved when:

- it is on the same line as "Policy Number", "Account number", "Plan",
  "Reference" and the like, but not on a line about the sender's own
  registration (such as an FCA firm reference); or
- it is a letter-and-digit number of ten or more characters that appears
  twice.

A number already saved for another folder is never overwritten. The conflict
is listed by `index show`. **Skip** saves nothing, because the PDF is not filed.

## Duplicates and conflicts

Nothing is overwritten or deleted.

- **Already filed:** a PDF whose content is already in the target folder,
  under any name, goes to the desktop Trash.
- **Name taken:** when a different file has the new name, the PDF stays in
  the inbox with an error.

## Requirements and logs

- Required: `pdftotext`, `pdftoppm` and `pdfinfo` (poppler-utils), and `gio`
  (libglib2.0-bin). zenity, feh and wmctrl are no longer used.
- Optional: `ocrmypdf` for scans without text.
- Python with organiseMyProjects and PySide6 (both in `py312`). `pdfFiler.sh`
  uses `PDF_FILER_PYTHON`, then the active `python3`, then the `py312` Conda
  environment. Use `pdfFiler/environment.yml` on a fresh machine.
- The window opens only when a PDF needs it, so `suggest`, `index show` and
  auto rules work without a display.
- Logs go to `~/.local/state/pdfFiler/`.

## Tests

```bash
cd pdfFiler && python -m pytest     # in py312
```

The tests use generated PDFs read by the real `pdftotext`, on temporary
cabinets:

- golden examples modelled on the Aviva tax letter, the MBNA renewal and the
  Aviva ISA statement (with fictional numbers), and on the Direct Payments
  rule;
- the form logic and the workflow, with a scripted window;
- the real Qt filing window, driven off-screen;
- the real `pdfFiler.sh`, run with no display.
