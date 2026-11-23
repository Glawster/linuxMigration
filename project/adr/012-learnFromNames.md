# 012: pdfFiler learns from names and confirmations, not filed content

- Status: Accepted
- Date: 2026-11-23
- Requirements: [005](../requirements/features/005-pdfFilerSuggestions.md)

## Context

To suggest where a scan belongs, pdfFiler could read every filed PDF and
compare text, or rely on what the cabinet's names already say. The cabinet
holds about 4,600 filed PDFs. Many are scans whose OCR text is poor, and
opening them all on every run is slow. The names already carry the useful
facts: plan and account numbers as folder names (`AV2550339`), and each
folder's labels and types in `<date> - <label> - <type>.pdf`.

## Decisions

1. **The index is built from names only**, on every run, walking the cabinets
   root and skipping `Inbox` and `Archive`. No filed PDF is opened.
2. **Identifiers** are tokens of six or more letters and digits that contain a
   digit, taken from folder names and from the label part of filed names.
3. **Confirmations add identifiers.** When a PDF is filed with `--confirm`,
   reference numbers in *its* text are saved against the chosen folder in
   `~/.config/pdfFiler/learned.json`. These are tokens on the same line as a
   label ("Policy Number", "Account number", "Plan", "Reference"), or
   letter-and-digit tokens of at least ten characters that appear twice,
   because OCR often moves the number away from its label. A number already
   saved for another folder is not overwritten; the conflict is kept and
   reported.
4. **No fuzzy matching.** Identifiers match exactly, ignoring case. An
   OCR-damaged number simply does not match, and the weaker evidence or the
   dialogs take over.

## Consequences

- Building the index costs a directory walk (well under two seconds for the
  current cabinet) and needs no cache.
- Suggestions improve as documents are filed, and every suggestion can say
  which name or number produced it.
- Documents whose names carry no identifier rely on folder-name words and
  rules until a confirmation teaches pdfFiler their number.
