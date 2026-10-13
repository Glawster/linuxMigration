# Current increment

Active requirement: [REQ-010](requirements/features/010-approved-mailbox-change-execution.md) (`InProgress`).

## Delivered

- Approved-plan validation and durable execution journaling.
- Exact, separately approved and idempotent IMAP destination creation.
- One explicitly confirmed personal live-year File action: copy, verify full
  destination content, then remove only the approved source UID.
- Durable copy/removal intent and conservative restart reconciliation without
  duplicate COPY, with executor exclusion for concurrent runs.
- Fake-mailbox tests for interruptions, failures and stale/unapproved actions.
- Moving Mail review now separates Action from destination Status, uses a compact
  selected-domain editor, keeps Parent and Folder on separate rows, and exposes
  `i` Ignore, `j` Junk, `f` File and `s` Sender override shortcuts without an
  action dropdown.

See [Execution boundary](../documentation/executionBoundary.md) for the API,
connection ownership, fresh-observation contract and uncertain-copy policy.
Normal discovery, planning and the TUI remain read-only. No real mail was changed.

## Remaining sequence

1. Broaden proven single-action execution to batches.
2. Add local Thunderbird archive copy -> verify -> remove.
3. Add supported Thunderbird-compatible Junk marking.

REQ-008 final approval and an explicit TUI Execute operation remain integration
dependencies. REQ-010 stays InProgress.
