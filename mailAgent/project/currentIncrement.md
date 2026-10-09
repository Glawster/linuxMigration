# Current increment

Active requirement: [REQ-009](requirements/features/009-read-inbox-filing.md) (`InProgress`).

## Delivered in Phase 1

- Moving Mail is a main-menu tab with durable mailbox-specific domain and sender rules.
- File resolves canonical archive destinations; Ignore and Junk record decisions without folder paths.
- Read-only plans separate folder moves from Ignore/Junk dispositions; unread mail remains excluded.
- The compact editor supports discovered/proposed parents and File, Ignore, and Junk choices.
- Responsive table sizing uses public Textual APIs.

## Remaining Phase 2

Execution remains disabled. Reviewed folder creation, IMAP moves, verified local
archival and Thunderbird-compatible junk marking require the execution controls
specified by REQ-004 and REQ-008.
