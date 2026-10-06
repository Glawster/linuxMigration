# REQ-008 - Plan resolution and approval

## Purpose

Turn the read-only migration plan into a durable, reviewable set of user
decisions before any mailbox mutation is implemented.

The user must be able to reduce the Review Queue over time without answering the
same classification questions after every plan refresh.

## Scope

This phase remains planning-only. It records decisions and applies them to
subsequent plans; it does not create folders, move mail, delete mail or alter
Thunderbird configuration.

The implementation is incremental:

1. resolve ambiguous sender classification against the canonical archive
   taxonomy;
2. record explicit Sent and Trash/Junk/Drafts policies;
3. approve or reject demand-driven IMAP mirror folders;
4. present a final approved plan suitable for a later execution phase.

## Sender classification decisions

- A Review Queue item with a normalized sender and no unambiguous canonical
  archive folder may be assigned to an existing canonical archive folder.
- The decision is mailbox-specific and sender-specific.
- For a legacy mailbox, the chosen canonical folder belongs to its configured
  personal migration target.
- Decisions persist independently of the generated plan.
- Refreshing the plan reuses the decision automatically.
- A user decision takes precedence over inferred archive-history sender
  classification.
- The resulting proposal records that the classification came from an explicit
  user decision.
- A decision never causes immediate mail movement.

## Persistence

Durable plan-resolution preferences are stored in:

`~/.config/mailAgent/plan-resolution.json`

The file:

- uses schema version 1;
- is written atomically;
- is created with user-only permissions;
- contains mailbox IDs, normalized sender addresses, target mailbox IDs and
  canonical folder names only;
- contains no credentials or message bodies.

## System-folder decisions

A later increment of this requirement must allow one explicit policy per
mailbox/system folder.

- Sent must map to a canonical archive folder before year-based planning.
- Trash/Junk/spam/Drafts require an explicit retention policy.
- Empty system folders may still have a policy so the decision does not recur.
- Policies must remain reviewable and reversible before execution.

## IMAP mirror approval

Mirror folders must be demand-driven rather than created simply because a
canonical local folder exists.

- Only propose a missing IMAP mirror when at least one live-year message needs
  that destination.
- The user can approve or reject the proposed mirror.
- Rejected mirrors remain non-executable and their affected messages stay in
  review.
- Approval alone does not create the folder; creation belongs to migration
  execution.

## Approval boundary

- Planning and resolution remain read-only with respect to mail.
- The plan must distinguish inferred proposals from explicit user decisions.
- No migration executor may act on unresolved Review Queue items.
- No migration executor may create an unapproved destination folder.
- Execution remains disabled until a separate execution requirement enables it.

## TUI

The Plan > Review Queue view must support resolving sender-classification items.

For the first increment:

- select a Review Queue row;
- choose one of the canonical folders belonging to the correct target mailbox;
- save the sender decision;
- refresh/rebuild the plan;
- show the resulting messages as proposals rather than repeating the same review
  item.

Non-sender review items remain visible until their corresponding policy
increment is implemented.

### Plan refresh UX

Refreshing an existing plan must not close the Mailbox Audit TUI while discovery
and planning run.

- Keep the current TUI mounted and responsive during the scan.
- Disable the Refresh Plan button while one refresh is already running.
- Show `Refreshing plan…` in the Plan summary while work is in progress.
- Run the blocking discovery/planning workflow away from the Textual UI loop.
- Replace the Summary, Mapping, Proposed Moves, Review Queue and Role Boundaries
  data in place when the refresh succeeds.
- Preserve the current Plan tab state and Proposed Moves filter control rather
  than rebuilding the application.
- Keep the previous plan visible if refresh fails and show the failure in the
  Plan summary area.
- A first plan, where no stored plan exists yet, may still use the original
  create-plan transition; subsequent Refresh Plan operations must remain in the
  mounted TUI.

## Acceptance criteria - first increment

- an ambiguous sender can be assigned to a canonical folder from the TUI;
- the decision persists across application restarts;
- Refresh Plan applies the stored decision;
- multiple messages from that sender in the same source mailbox reuse the
  decision;
- a legacy sender decision targets only the configured personal migration
  target;
- an invalid/nonexistent canonical destination is ignored safely;
- explicit sender decisions are identifiable in the generated proposal;
- no email or Thunderbird state changes when a decision is saved;
- malformed resolution storage is reported safely rather than silently used;
- refreshing an existing plan leaves the TUI mounted while the scan runs.

## Proposed Moves presentation

The Proposed Moves view must remain compact enough to review comfortably in a
terminal.

- Group visually identical message-level proposals and show a message count.
- Keep the individual proposals in the structured plan for later execution.
- Show the source explicitly as an IMAP location, for example
  `andy IMAP/INBOX`.
- Show local archive destinations using the archive store name, for example
  `myMail/Finance/Mark Bates`.
- Show live destinations explicitly as IMAP, for example
  `andy IMAP/Finance/Mark Bates`.
- Decode IMAP modified UTF-7 for display so a literal ampersand encoded as
  `&-` is shown to the user as `&`; retain the original encoded server name
  in the structured plan.
- Do not describe a missing live folder generically as `create destination
  folder`; use `create IMAP mirror`.
- Prefer concise reason labels in the table while retaining full evidence in the
  structured plan.
- Provide a case-insensitive free-text filter over source, sender, year,
  destination and reason so the user can focus on a subset without altering the
  underlying plan.
- Show how many grouped moves match the current filter.
