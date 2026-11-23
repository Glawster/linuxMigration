# Prompt 005: implement pdfFiler suggestions

- Requirement: [005 Suggest where a scanned PDF is filed](../features/005-pdfFilerSuggestions.md)
- Role: implement and test
- Decisions: two ADRs to write first (see Assignment); [ADR 008](../../adr/008-repositoryVersion.md)

## Assignment

1. Write the two pending ADRs named in the requirement and add them to
   `project/adr/adrIndex.md`: moving `pdfFiler` to a Python project, and
   learning from names only.
2. Implement `pdfFiler` as a Python project that suggests the folder, label,
   type and date of each inbox PDF from the cabinet's names and from rules,
   and files it after one confirmation. Satisfy every acceptance criterion in
   the requirement.
3. Express the Direct Payments statements as a rule and show it gives the same
   result as `fileDpStatements`.

## Constraints

- Keep every `1.4a6` safety guarantee: preview by default (`-y`/`--confirm`
  to act), never overwrite, already-filed content to the Trash, move rather
  than delete.
- Build the index from names only; never open filed PDFs. Reference numbers
  learned from confirmed filings go to `~/.config/pdfFiler/learned.json` and
  are saved only with `--confirm`.
- Core logic (index, matching, naming, type, dates, rules) must not import the
  GUI layer and must be testable without it.
- Use organiseMyProjects logging (`setApplication`, `runStart`, `line`), with
  no fallback logger.
- Never commit real documents or real personal details as test data; generate
  fixtures with `tests/pdfFixtures.py`.

## Component boundaries

- Implementation: a `pdfFiler/` project folder, as agreed in the ADR,
  following `documentation/repositoryLayout.md`.
- Tests: that project's `tests/`, including golden tests for the Aviva
  example, the MBNA renewal (same-named folders and a learned policy number)
  and the Direct Payments rule.
- Documentation: `documentation/pdfFiler.md`, README entries and release
  notes.

## Verification commands

```bash
python3 -m pytest            # in the project's environment
shellcheck pdfFiler.sh       # while the Bash version remains
```

## Handoff evidence

- Test results and the golden-test outputs.
- `pdfFiler index show` output and its timing against the real cabinet.
- The suggested paths for the real Aviva and MBNA letters in the inbox,
  previewed with nothing moved.
