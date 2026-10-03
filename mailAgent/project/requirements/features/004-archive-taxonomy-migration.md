# REQ-004 - Archive taxonomy and mail migration

## Purpose

Use the existing local archive structure as the canonical taxonomy for the
personal mailboxes while respecting shared and support mailbox boundaries.

## Mailbox roles

The application supports:

- `personal`
- `legacy`
- `shared`
- `support`

## Initial mailbox behaviour

### Andy current - personal

`andyw@glawster.com`

- live-year mail remains on IMAP;
- pre-live-year mail is archived under local `myMail`;
- live IMAP folders may mirror the established `myMail` taxonomy.

### Kathy - personal

`kathyw@glawster.com`

- live-year mail remains on IMAP;
- pre-live-year mail is archived under local `kathyMail`;
- live IMAP folders may mirror the established `kathyMail` taxonomy.

### Andy old - legacy

`andy@glawster.com`

- live-year mail is proposed for migration to Andy current;
- older mail is proposed for migration into `myMail`;
- it is not a normal destination mailbox.

### HWFC - shared

`info@hillsboroughwalkingfootball.com`

- mailbox is accessed by multiple people;
- preserve its own shared server taxonomy;
- never apply Andy/Kathy personal filing structure to it;
- discover existing folders and filters before proposing organisation;
- any future local archival needs a separate shared retention policy;
- server-side moves remain reviewable and safe-by-default.

### Clann Eolas - support

`info@clanneolas.com`

- mailAgent may access, inspect, search, highlight and classify mail;
- it is excluded from REQ-004 archive migration;
- do not mirror a local personal archive into it;
- do not automatically move historical mail off the server;
- do not restructure it as part of personal mailbox migration.

## Functional requirements

1. Support the four mailbox roles above.
2. Keep role behaviour explicit in configuration.
3. Apply `liveYear` retention only to `personal` and appropriate `legacy`
   migration workflows.
4. Discover existing local archive structure for personal mailboxes.
5. Treat that structure as the canonical personal taxonomy.
6. Propose IMAP mirrors for live-year personal mail where appropriate.
7. Build migration proposals for the legacy mailbox.
8. Exclude support mailboxes from archive/migration planning.
9. Keep shared mailbox planning independent of personal archive rules.
10. Put ambiguous personal/legacy classifications into a review queue.
11. Default to planning only.
12. Require explicit confirmation for future mailbox mutations.
13. For IMAP-to-local archival, copy and verify before removing the server copy.
14. Record completed operations in persistent state.

## Acceptance criteria

- `clannEolas` produces no personal archive migration proposals.
- `hwfc` produces no mappings into `myMail` or `kathyMail`.
- `andy` and `kathy` follow the live-year/local-archive split.
- `old` targets Andy current for live-year mail and `myMail` for older mail.
- shared/support roles remain readable in the TUI.
- no mailbox mutation occurs in planning mode.

## Delivery status

The planning-only increment is implemented: explicit role validation,
read-only archive/message discovery, canonical mappings, legacy migration
proposals, review queue, persistent plan snapshots and TUI review panels.
Shared/support accounts are excluded from personal planning.

Execution remains disabled as permitted by the implementation prompt. Actual
copy/verification/removal and completed-operation persistence belong to a future
execution increment. See [implementation and limitations](../../../documentation/mailboxModel.md#implemented-planning-workflow).


## REQ-004 refinement

- Aggregate system-folder review items by mailbox/folder, with message counts.
- Exclude Trash/Junk/Drafts from header scans and normal archive mapping;
  require one explicit future retention decision per folder. Legacy
  `INBOX.Trash` follows this policy initially.
- Retain individual review exceptions for meaningful message-specific issues.
- Sent requires an explicit canonical folder mapping; once mapped, apply the
  normal year split and legacy target policy. Otherwise review once per folder.
- Include migrationPlan summary counts for messages scanned, proposals, review
  items, system-folder messages excluded, and messages with invalid dates.
  Report unknown system-folder counts separately.
- Keep all execution disabled.


## User-readable plan summary

The planning output must include a concise `userSummary` near the start of
`migrationPlan` so a user does not need to interpret the detailed message-level
JSON.

The summary must:

- state clearly that planning is read-only and no mail has been changed;
- show messages scanned, proposed actions, and review-item counts;
- show per-mailbox counts for proposals, review items, unclassified messages,
  and proposed IMAP mirror folders;
- aggregate message-level review failures by mailbox and reason;
- list folder-level decisions still required, including Sent mappings and
  future Trash/Junk/Drafts retention;
- provide short next-step guidance based on the actual plan;
- contain no passwords, message bodies, or other credential data;
- preserve the detailed plan arrays for diagnostics and machine use.
