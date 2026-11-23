# 005: Suggest where a scanned PDF is filed

## Status

InProgress

## Outcome

As the person filing scanned post, I need `pdfFiler` to suggest the cabinet
folder, name, document type and date of each inbox PDF from what is already
filed, so that most documents are filed with a single confirmation instead of
three dialogs, and are named consistently with their neighbours.

## Context

- Documents are scanned with gscan2pdf (ScanSnap S1300i, OCR by tesseract)
  into `~/Documents/myCabinets/Inbox` and filed with `pdfFiler.sh`, which
  asks for the folder, type and date of every PDF (fixed and brought up to the
  guidelines in `1.4a6`; [guide](../../../documentation/pdfFiler.md)).
- The cabinet already records where documents belong. Plan and account
  numbers appear as folder names (`Finance/Aviva/AV2550339`), and filed names
  follow `<date> - <label> - <type>.pdf`, for example
  `2025-05-14 - Aviva, AV2550339 - Statement.pdf`.
- A read-only prototype on 2026-11-23 learned 30 identifiers from the names of
  4,627 filed PDFs. It placed the Aviva tax letter in the inbox in
  `Finance/Aviva/AV2550339` because page 1 contains `AV2550339`. It found the
  folder's label `Aviva, AV2550339` (28 files) and types `Letter From`,
  `Statement`, `Tax` and `Review`.
- The same letter shows two gaps. `pdfFiler.sh` reads its date as
  `2025-04-06`, the start of the tax period, but earlier Aviva tax documents
  are dated at the end of the tax year (`2025-04-05`). gscan2pdf named the
  file by scan date (`2026-11-23.pdf`), so the name gives no date.
- Two recent files in that folder (`2025-08-15 - AV2550339 - Statement.pdf`,
  `2025-11-17 - AV2550339 - Statement.pdf`) break the folder's naming because
  the folder name was used as the label.
- `fileDpStatements` is a hand-written rule of exactly this kind: an account
  number on page 1 decides the folder, year subfolder, name and date.
- OCR text contains errors ("Piease"). Long identifiers such as `AV2550339`
  usually survive and are the strongest evidence.
- A second scan the same day, an MBNA Home Emergency renewal (policy
  `MBNAUKM4HAP604983305`, letter dated `20/10/2025`), shows three gaps:
  - Its policy number appears in no name, so there is no identifier match.
  - "MBNA" names two folders: `Finance/MBNA` (39 credit-card files) and
    `Insurance/MBNA` (one file, `2025-10-29 - Insurance, MBNA - Policy
    Documents.pdf`). Counting files would pick the wrong one; the words
    "insurance" and "policy" in the letter point to `Insurance/MBNA`.
  - The right type, `Renewal`, has never been used in `Insurance/MBNA`.

  `pdfFiler.sh` already reads its date correctly as the letter date,
  `2025-10-20`, not the renewal date.
- A third scan, an eight-page Aviva ISA statement for account `AV2585522`
  ("Statement for 23/02/2026 to 22/05/2026"), matches its folder by
  identifier, including the `AV2585522-001` sub-account references. It shows
  two date gaps:
  - Filed statements are dated at the end of their period (`2025-05-22`,
    `2024-02-22`). `pdfFiler.sh` reads `2026-05-22` only because OCR happened
    to put "to 22/05/2026" before "for 23/02/2026".
  - OCR misread one date as `23/02/2028`, a valid calendar date in the
    future.

  Its document reference `PDOEA02-20260524-21923-000145` embeds `20260524`
  and must not be taken as the date. Pages 7 and 8 are blank backs of duplex
  sheets.

## Scope

- **Cabinet index:** learned on each run from folder and file *names* only
  under the cabinets root, excluding `Inbox` and `Archive`. It records
  identifiers (tokens of six or more characters containing a digit) from
  folder names and filed-name labels, each folder's labels and types with
  their counts, and folder names usable as words.
- **Matching:** scores each folder from page 1 and 2 text.
  - Strongest: an identifier in the index.
  - Weaker: a folder's name found as a whole word.
  - Overriding both: rules in `~/.config/pdfFiler/config.json`, following the
    user config pattern.

  Each suggestion keeps the reason that produced it.
- **Choosing between folders with the same name:** when folders score
  equally (`Finance/MBNA` and `Insurance/MBNA`), the words of the rest of each
  folder's path found in the text decide ("insurance", plus the
  folder-specific keywords "policy", "cover" and "premium" for
  `Insurance`). The runner-up is kept and offered under **Change…**.
- **Learning from confirmations:** when a PDF is filed, reference numbers
  found next to labels such as "Policy Number", "Account number", "Plan" or
  "Reference" in *that* PDF's text are saved against the chosen folder in
  `~/.config/pdfFiler/learned.json`. They then count as identifiers, so the
  next letter about the same policy matches strongly. A number already saved
  against a different folder is not overwritten; the conflict is logged and
  shown by `pdfFiler index show`.
- **Naming:** the label is the folder's most used label (`Aviva, AV2550339`),
  falling back to the folder name. A year folder uses its parent, as in
  `1.4a6`.
- **Type:** chosen from the standard type list (the `1.4a6` list plus any
  type used in the cabinet's names) by keyword evidence in the text
  (statement, tax, renewal, policy schedule, certificate of insurance, P60,
  payslip, invoice, receipt). It is not limited to the types already used in
  the chosen folder. The folder's own types settle ties. With no evidence,
  the folder's most used type is used.
- **Date strategy per type**, settable by rules:
  - the `1.4a6` reading for most types;
  - for `Tax`, the end of the UK tax year (5 April) that the document covers;
  - for `Statement`, the end of the stated period: the date after "to" in
    "for/from X to Y" or "Period … to …", found even when OCR splits or
    reorders the lines. Falls back to the `1.4a6` reading;
  - for a rule, a named strategy such as `standaloneLine` (bank statements).
- **Future dates rejected:** for every strategy, a candidate date later than
  the day the PDF is filed is never used as the document date. Dates inside
  longer references (such as `PDOEA02-20260524-…`) are never read from the
  text; the file-name fallback is unchanged.
- **Rules:** each has text to match, a target folder (optionally with a
  `{year}` subfolder), a label, a type, a date strategy and an optional
  `auto` flag. The Direct Payments statements become a rule, so
  `fileDpStatements` can be retired or kept as a shortcut.
- **One filing window** ([ADR 013](../../adr/013-filingWindow.md)): page 1
  of the PDF beside the folder (with the other likely folders and Browse…),
  type, date and label, all filled in and editable. The full filed name is
  shown on one line and updates as the fields change. It also shows the
  reason ("matched AV2550339"), with **File**, **Skip** and **Stop**.
- **Automatic filing:** with `--confirm`, a PDF matched by a rule marked
  `auto` is filed without dialogs. Without `--confirm` nothing moves, as
  today.
- All `1.4a6` safety behaviour is kept: preview by default, never overwrite,
  already-filed content to the Trash, decline moves on.
- A Python implementation with GUI-free core logic, CLI subcommands such as
  `pdfFiler inbox file` and `pdfFiler index show`, and organiseMyProjects
  logging.

## Out of scope

- Reading the content of already-filed PDFs to learn from (names only). The
  text of the PDF being filed is read at filing time, as today.
- Fuzzy matching of OCR-damaged identifiers.
- Machine learning or any online service. Everything runs locally.
- Renaming existing inconsistently named files (a candidate for a separate
  requirement).
- The scanner's hardware button, and gscan2pdf configuration.
- Changing the PDF itself, including removing blank pages. Blank duplex backs
  are removed at scan time (gscan2pdf's unpaper clean-up, or `ADF Front` for
  one-sided post).
- Committing real personal documents to the repository as test data.

## Acceptance criteria

1. Given a filed folder named `AV2550339` and an inbox PDF whose page 1
   contains `AV2550339`, when suggestions are made, then that folder is
   suggested first, with the reason naming `AV2550339`.
2. Given no identifier match but a folder named `Aviva` and text containing
   the word "Aviva", when suggestions are made, then that folder is
   suggested, ranked below any identifier match.
3. Given a rule whose text matches, when suggestions are made, then the rule's
   folder, label, type and date strategy are used ahead of any learned
   suggestion.
4. Given a folder whose most used label is `Aviva, AV2550339`, when a PDF is
   filed there, then its name uses that label, not the folder name.
5. Given text containing "tax" evidence and a folder whose types include
   `Tax`, when the type is chosen, then it is `Tax`. Given text containing
   "renewal" evidence and a folder that has only used `Policy Documents`, then
   it is `Renewal`. Given no keyword evidence, it is the folder's most used
   type.
6. Given a `Tax` document covering 6 April 2025 to 5 April 2026, when the date
   is chosen, then it is `2026-04-05`.
7. Given a suggestion, when the PDF is offered, then one window shows page 1,
   the fields filled in with the suggestion, the full destination on one
   line, and the reason. **File** files it. Changing any field updates the
   destination at once, and choosing another folder recalculates the label,
   type and date that were not typed in.
8. Given a rule marked `auto` and `--confirm`, when the inbox is filed, then
   the matching PDF is filed with no dialog. Without `--confirm`, nothing
   moves.
9. Given a PDF with no suggestion, when it is offered, then the same window
   is shown with the folder empty, and **File** is disabled until a folder
   inside the cabinets is chosen.
10. Given an existing different file at the proposed path, or identical
    content already in the folder, when filing, then the `1.4a6` behaviour
    applies (left in the inbox, or sent to the Trash).
11. Given the current cabinet (about 4,600 filed PDFs), when the index is
    built, then it takes under two seconds and opens no PDF.
12. Given `pdfFiler index show`, when run, then it lists the learned
    identifiers with their folders (and whether each came from a name or a
    confirmation), each folder's labels and types, and any conflicting saved
    numbers, for review.
13. Given folders `Finance/MBNA` (39 files) and `Insurance/MBNA` (one file),
    and an inbox PDF containing "MBNA", "insurance" and "policy", when
    suggestions are made, then `Insurance/MBNA` is suggested first with
    `Finance/MBNA` as the runner-up under **Change…**.
14. Given a PDF filed into `Insurance/MBNA` whose text contains
    "Policy Number: MBNAUKM4HAP604983305", when the next inbox PDF contains
    `MBNAUKM4HAP604983305`, then `Insurance/MBNA` is suggested first with the
    reason naming that number. Without `--confirm`, nothing is saved to
    `learned.json`.
15. Given a `Statement` whose text contains "for 23/02/2026" and
    "to 22/05/2026" in either order, on separate lines, when the date is
    chosen, then it is `2026-05-22`.
16. Given text whose only plausible date is in the future (for example OCR's
    `23/02/2028` on 2026-11-23), when the date is chosen, then that date is
    not used: an earlier valid date in the text is used, or the file name, or
    the user is asked.
17. Given the reference `PDOEA02-20260524-21923-000145` in the text, when the
    date is chosen, then `2026-05-24` is not taken from it.

## Dependencies and decisions

- Builds on `pdfFiler.sh` as delivered in `1.4a6` (branch
  `feature/pdf-filer-update`).
- [ADR 011: pdfFiler moves to a Python project](../../adr/011-pdfFilerPython.md).
- [ADR 012: pdfFiler learns from names and confirmations, not filed content](../../adr/012-learnFromNames.md).
- [ADR 013: One tkinter filing window replaces the zenity dialogs](../../adr/013-filingWindow.md).
- [ADR 008: One version and release tag for the whole repository](../../adr/008-repositoryVersion.md)
  (version reporting).

## Verification

- Unit tests for the index, identifier extraction, scoring, label and type
  choice, and date strategies, on a temporary cabinet built in `tmp_path`.
- A golden test: a generated PDF reproducing the relevant text of the Aviva
  tax letter (no real personal data), filed against a temporary cabinet
  shaped like `Finance/Aviva/AV2550339`. Expected result:
  `Finance/Aviva/AV2550339/2026-04-05 - Aviva, AV2550339 - Tax.pdf`.
- A golden test: a generated PDF reproducing the relevant text of the MBNA
  Home Emergency renewal, against a temporary cabinet with both
  `Finance/MBNA` and `Insurance/MBNA`. Expected result:
  `Insurance/MBNA/2025-10-20 - Insurance, MBNA - Renewal.pdf`, with
  `Finance/MBNA` as runner-up. Then a second PDF with the same policy number
  matches by the learned number.
- A golden test: a generated PDF reproducing the relevant text of the Aviva
  ISA statement, with the period lines in reversed order, an OCR-damaged
  future date, the `PDOEA02-20260524-…` reference and `AV2585522-001`
  references. Expected result:
  `Finance/Aviva/AV2585522/2026-05-22 - Aviva, AV2585522 - Statement.pdf`.
- A golden test for the Direct Payments rule, matching `fileDpStatements`.
- Tests of the real filing window on the display (criteria 7 and 9), and of
  the workflow with a scripted window and the real form, filing and `gio`
  double (criteria 7 to 10).
- Timing check of `pdfFiler index show` against the real cabinet (criterion
  11).
- Manual acceptance: file the real Aviva letter from the inbox, then a mixed
  batch of a week's post.

## Change history

- 2026-11-23: created from the review of `pdfFiler.sh` (Stage 2) and the
  Aviva letter scanned that day; prototype results recorded in Context.
- 2026-11-23: refined before delivery from a second scan (MBNA Home
  Emergency renewal). Added choosing between folders with the same name,
  types beyond those already in the folder, and learning reference numbers
  from confirmed filings (criteria 5, 12, 13 and 14).
- 2026-11-23: refined before delivery from a third scan (Aviva ISA
  statement). Added the `Statement` period-end date, rejection of future
  dates and of dates inside references, and put blank-page removal out of
  scope (criteria 15, 16 and 17).
- 2026-11-23: implemented on `feature/pdf-filer-suggestions` (`1.4a7`) with
  ADRs 011 and 012. 85 tests pass in `pdfFiler/tests`. The index of the real
  cabinet takes 0.09 s (961 folders, 4,626 PDFs). The three real scans are
  previewed as in the golden tests. Manual acceptance is still to do.
- 2026-11-23: after the first real run, the zenity confirmation was replaced
  by one filing window (ADR 013) at the user's request, with the filed name on
  one line. Criteria 7 and 9 were revised.
