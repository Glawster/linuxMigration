# MA-012 Rolling IMAP retention and local archive aging

Status: ToDo

## Purpose

Replace the fixed calendar-year IMAP retention rule with a rolling retention
window so that recent personal mail remains available on every IMAP-connected
device while older mail is aged into the authoritative local Thunderbird
archive.

The initial retention period is 12 calendar months. A message remains on IMAP
until its message date is older than the calculated cutoff date. Once outside
the retention window, it becomes eligible to move from IMAP into the approved
canonical folder in the authoritative local archive.

This requirement builds on REQ-009 filing policy and REQ-010 verified execution.
It does not weaken the existing copy -> verify -> remove safety boundary.

## Scope

MA-012 applies only to personal mailboxes with an authoritative local archive.
For the current installation:

- Andy's authoritative local archive is `myMail`;
- Kathy's authoritative local archive is `kathyMail`.

Shared and support mailboxes are excluded unless a later requirement defines an
explicit retention policy for them.

The requirement covers two related decisions:

1. where newly filed personal mail should live according to its age; and
2. how mail already on IMAP should be aged out when it passes the retention
   cutoff.

## Retention policy

Add a configurable rolling IMAP retention period. The initial policy is 12
calendar months.

Suggested configuration:

```toml
[general]
imapRetentionMonths = 12
```

The cutoff is calculated from the current local calendar date by subtracting the
configured number of calendar months. It is not a fixed number of days.

For example, on 13 October 2026 with a 12-month retention period:

```text
cutoff: 13 October 2025

2026-09-01  -> IMAP
2026-01-10  -> IMAP
2025-11-20  -> IMAP
2025-09-30  -> local archive
```

A message dated exactly on the cutoff date remains within the retention window.
A message older than the cutoff is eligible for local archival.

## Filing destination policy

REQ-009 filing should eventually use the rolling cutoff instead of the current
fixed `liveYear` rule.

For a resolved File decision:

```text
message date within retention window
    -> source mailbox's approved IMAP canonical folder

message date older than retention window
    -> approved canonical folder in the authoritative local archive
```

The canonical taxonomy remains unchanged. Server namespace details such as an
`INBOX.` prefix and `.` delimiter are transport details and must not leak into
the canonical archive path.

A canonical folder such as:

```text
Cars/Rivervale
```

may therefore map to:

```text
IMAP:        INBOX.Cars.Rivervale
local store: Cars/Rivervale
```

## Retention reconciliation

A separate retention reconciliation workflow must inspect existing personal IMAP
folders and identify messages that have aged beyond the configured cutoff.

This is distinct from Inbox filing. Running Inbox cleanup must not silently age
unrelated already-filed IMAP messages into the local archive.

The reconciliation should:

1. scan configured personal IMAP folders using the existing canonical mapping;
2. determine each message's effective date using the same date rules used by
   filing eligibility;
3. identify messages older than the rolling cutoff;
4. resolve the corresponding canonical local archive destination;
5. report proposed archival actions without mutation;
6. require explicit execution approval before moving mail.

Messages whose date or canonical destination cannot be determined safely remain
on IMAP and are reported for review.

## Execution

Execution must reuse the REQ-010 safety model.

For each approved retention action:

1. revalidate the source mailbox, folder, UIDVALIDITY and UID;
2. revalidate the message date and retention cutoff;
3. revalidate the approved local archive store and canonical destination;
4. copy the complete message to the authoritative local Thunderbird archive;
5. verify that the local copy is readable and corresponds to the intended source
   message;
6. remove the source IMAP message only after successful local verification;
7. persist the result in the execution journal.

If verification fails, the source remains on IMAP.

An interrupted or uncertain operation must reconcile current state before any
copy or removal is repeated. A retry must not duplicate the local archive copy.

## Archive-store policy

The default archive destination remains tied to the personal mailbox:

```text
Andy source  -> myMail
Kathy source -> kathyMail
```

An explicit REQ-009 cross-archive override may still select the other configured
authoritative personal archive. Retention aging must preserve that approved
archive-store decision and must not infer a cross-archive destination from folder
names alone.

The local archives remain single authoritative stores on the machine hosting
mailAgent. MA-012 does not introduce archive replication or synchronisation to
other client devices.

## Availability consequence

IMAP is the shared recent-mail view. Local archives are long-term storage.

When a message ages out of IMAP and is successfully archived locally, it is no
longer expected to remain visible on IMAP-only devices. This is intentional.

The TUI must make the consequence clear before execution, particularly for
Kathy's mailbox where old mail moved into `kathyMail` will no longer be visible
from her MacBook or another IMAP-only client.

## Review and TUI

Add a read-only retention review, separate from normal Inbox filing and separate
from mutation execution.

The review should show at least:

- mailbox;
- configured retention period;
- current cutoff date;
- number of messages outside the retention window;
- number of canonical folders affected;
- unresolved/blocked count;
- destination archive store;
- estimated actions requiring local folder creation where applicable.

A future execution view may process the approved actions in batches, but the
first implementation should preserve the proven REQ-010 approach and start with
small explicitly reviewed batches.

## Configuration migration

Do not remove or reinterpret `general.liveYear` while REQ-010 execution remains
under active validation.

Introduce `imapRetentionMonths` as a separate policy and migrate filing logic in
a controlled increment once the rolling-date tests and retention reconciliation
are proven.

During transition, configuration validation must reject ambiguous combinations
rather than silently changing where mail is stored.

The final design should remove the need for an annually updated `liveYear`
retention decision while retaining any year value still required for unrelated
reporting or migration compatibility.

## Safety and exclusions

MA-012 must not:

- automatically archive mail merely because the TUI starts;
- perform retention mutation during ordinary discovery, audit or plan refresh;
- use receipt time or current UID order as a substitute for a missing safe
  message date;
- delete an IMAP message before its local archive copy is verified;
- use global IMAP `EXPUNGE` as a fallback for exact-message removal;
- modify shared or support mailboxes;
- create or synchronise additional local archive copies on other devices;
- silently change a user-approved cross-archive destination.

## Audit state

Retention execution must use durable execution state under
`~/.local/state/mailAgent/` and record enough information to explain each aged
message without storing message bodies, credentials or secrets.

At minimum retain:

- action id;
- source mailbox/folder/UIDVALIDITY/UID;
- message date used for retention eligibility;
- cutoff date and configured retention period;
- canonical destination;
- destination archive store;
- start/completion timestamps;
- verification result;
- blocked/failure reason where applicable.

## Acceptance criteria

- a configurable rolling retention period exists, initially 12 calendar months;
- the cutoff uses calendar-month arithmetic rather than a fixed 365-day period;
- a message on the cutoff date remains on IMAP and an older message becomes
  archive-eligible;
- recent personal mail files to the source mailbox's canonical IMAP destination;
- older personal mail files to the approved authoritative local archive;
- already-filed IMAP mail can be reviewed for age-out independently of Inbox
  filing;
- retention review is read-only and reports proposed actions before mutation;
- unresolved date or destination identity blocks the action rather than guessing;
- local archival uses copy -> verify -> remove;
- failed local verification leaves the IMAP source unchanged;
- interrupted execution is retry-safe and does not duplicate archive copies;
- source mailbox, archive store and canonical destination are all revalidated;
- explicit REQ-009 cross-archive overrides remain supported for local archival;
- IMAP namespace details remain separate from the canonical folder taxonomy;
- aging old mail locally is allowed to make it unavailable to IMAP-only devices;
- shared/support mailboxes are not mutated;
- `liveYear` is not removed until the rolling policy has been introduced and
  validated without destabilising REQ-010;
- tests cover month-end and leap-year cutoff calculations, exact-boundary dates,
  missing/invalid dates, mapping failures, interrupted copy/verification and
  retry behavior;
- full project tests and checks pass before integration.

## Implementation guidance

Keep the rolling cutoff calculation, retention-plan generation, local archive
execution and Textual presentation separate.

Suggested increments:

1. introduce and test retention configuration and calendar-month cutoff logic;
2. produce a read-only retention reconciliation plan;
3. integrate rolling cutoff into new Inbox File destination decisions;
4. execute one approved IMAP-to-local retention action using REQ-010 primitives;
5. add retention review/progress presentation;
6. broaden to safe batches after single-message execution is proven.

Do not make MA-012 implementation part of the current REQ-010 stabilization
unless a required compatibility hook is identified explicitly.
