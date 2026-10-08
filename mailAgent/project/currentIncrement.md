# Current increment

Active requirement: [REQ-009](requirements/features/009-read-inbox-filing.md) (`InProgress`).

## Delivered in this increment

- **Moving Mail** is a Mailbox Audit main-menu tab. Inbox Digest no longer contains Filing.
- The Moving Mail editor shows the parent, folder and action labels on one-row fields.

## Agreed, not yet implemented

- **Ignore** leaves the matching read Inbox mail in the Inbox. It is not a folder move and it does not delete mail.
- **Junk** marks the matching read Inbox mail as junk so Thunderbird's junk filter can use it. It is not a move to a folder, it does not create a Thunderbird filter, and it does not delete mail.
- Phase 1 still must not change message flags or mailbox contents when those dispositions are recorded.
- Phase 2 execution remains disabled.
