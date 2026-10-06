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

The Plan > Role Boundaries view must include every configured mailbox, not only
mailboxes excluded from personal migration. It must state the role and concise
policy so the user can verify how each mailbox participates in the plan.

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
15. Show every configured mailbox and its role policy in Role Boundaries.
16. Allow Inbox sender domains to be assigned to canonical personal archive
    folders.
17. Discover candidate parent folders from the first level of each personal
    local archive taxonomy.
18. Allow a new parent folder to be proposed when no existing parent is suitable.
19. Keep domain-to-folder assignments mailbox-specific so `myMail` and
    `kathyMail` may have different filing structures.
20. Treat all new parent/child archive folders as proposals until a future
    execution phase explicitly creates them.

## Acceptance criteria

- `clannEolas` produces no personal archive migration proposals.
- `hwfc` produces no mappings into `myMail` or `kathyMail`.
- `andy` and `kathy` follow the live-year/local-archive split.
- `old` targets Andy current for live-year mail and `myMail` for older mail.
- personal, legacy, shared and support mailboxes all appear in Role Boundaries.
- shared/support roles remain readable in the TUI.
- sender domains can be mapped to canonical folders beneath discovered parents.
- only first-level archive folders are offered as discovered parents.
- a new parent can be proposed without immediately creating it on disk.
- one domain mapping applies to all matching senders for that personal mailbox.
- domain mappings for `myMail` do not implicitly apply to `kathyMail`, and vice
  versa.
- no mailbox or archive mutation occurs in planning mode.

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

`mailAgent --plan` must present a concise human-readable summary through
`organiseMyProjects.logUtils`. The user must not need to inspect the detailed
JSON to understand the plan.

The console summary must:

- state clearly that planning is read-only and no mail has been changed;
- show messages scanned, proposed actions, review-item counts, and excluded
  system-folder message counts;
- show per-mailbox counts for proposed actions, review items, unclassified
  messages, and proposed IMAP mirror folders where relevant;
- aggregate message-level review failures by mailbox and reason;
- list folder-level decisions still required, including Sent mappings and
  future Trash/Junk/Drafts retention;
- provide short next-action guidance based on the actual plan;
- contain no passwords, message bodies, or other credential data.

Presentation must remain separate from planning logic: `migrationPlanning.py`
produces structured data and a presentation module renders that data through
`logUtils`.

### JSON output

JSON is machine-readable diagnostic/export output, not the primary user
presentation.

- JSON must never be printed to stdout.
- `mailAgent --plan --json` writes to the default plan JSON file under the
  configured state directory.
- `mailAgent --plan --json FILE` writes to the requested file.
- The human-readable `logUtils` summary is still shown when JSON output is
  requested.
- JSON writing must not mutate mail.
- The detailed structured plan remains in JSON for diagnostics and scripting.

## Archive-history sender classification

When the current IMAP folder does not identify a canonical archive destination,
mailAgent may use the existing local archive as filing evidence.

- Build a sender-to-canonical-folder index from local archive message headers.
- Prefer an exact sender address that has historically been filed consistently
  in one canonical folder.
- A strong historical majority may be used when the sender appears in more than
  one folder; the proposal must retain the evidence count and explanation.
- If no historical sender evidence exists, a sender address containing a unique
  canonical folder leaf may be used as a medium-confidence proposal. For
  example, an address containing `paypal` may map to `Finance/PayPal` when that
  is the unique matching canonical folder.
- Ambiguous or weak matches remain in the review queue.
- Legacy mail uses the archive history of its configured personal migration target.
- Classification uses headers only and never reads message bodies for this purpose.
- Every inferred proposal records its classification method, confidence and reason.

## Domain-based sender filing

The Inbox sender list may also be used to define durable domain-level archive
filing rules for personal mailboxes.

- Derive a normalized registrable-looking domain from each sender address for
  grouping and presentation, while retaining the exact sender address for audit
  purposes.
- Group senders by domain so one filing decision can apply to all matching
  senders in that personal mailbox.
- If the domain already maps unambiguously to an existing canonical archive
  folder, reuse that folder rather than proposing a duplicate.
- Otherwise allow the user to assign the domain beneath one of the personal
  archive's discovered first-level parent folders, such as `Cars`, `Finance` or
  `Shopping`.
- Discover parents independently from `myMail` and `kathyMail`; do not assume
  the two archives have identical taxonomies.
- Only first-level canonical archive folders are presented as parent choices.
  Nested folders such as `Shopping/Amazon/Orders` contribute `Shopping` as the
  parent, not `Amazon` or `Orders`.
- If no existing parent is suitable, offer `Add parent…`. The entered value is
  recorded as a proposed canonical parent for that personal archive.
- Propose a child folder beneath the selected parent using a concise,
  user-editable business/domain label, for example `bmw.com -> Cars/BMW`.
- Distinguish existing folders, proposed child folders, and proposed parent +
  child folders in the plan.
- Persist the domain-to-canonical-folder decision separately from credentials.
- Domain filing decisions are planning metadata only in this increment: they do
  not create Thunderbird/local archive folders, create filters, or move mail.
- A later execution requirement may use the approved mapping to create folders,
  suggest filters and move/archive mail safely.


## Stored plan and refresh

The most recent read-only migration plan must be persisted automatically under
the configured mailAgent state directory so the user does not have to rescan
mailboxes merely to review the previous plan.

- Store the latest migration plan in `latest-plan.json`.
- Loading the normal TUI should reuse that stored plan when one exists.
- Show when the stored plan was generated.
- When no plan exists, show `Refresh Plan`.
- When a stored/current plan exists, show `Refresh Plan`.
- Refresh performs a fresh read-only discovery and replaces the stored plan.
- Persisting or refreshing a plan must not enable migration execution and must
  not require `--confirm`.
- A malformed or unsupported stored-plan schema must fail safely rather than be
  silently interpreted.
