# REQ-009 - Read Inbox filing

## Purpose

Use mailAgent as the primary filing engine for personal mailboxes so that the
Inbox remains a working queue:

- unread Inbox mail remains in the Inbox;
- read Inbox mail is eligible for filing;
- filing uses the canonical local archive taxonomy defined by REQ-004;
- sender/domain filing decisions are reusable and reviewable;
- Thunderbird filters are not required for mailAgent-managed filing.

This requirement introduces the filing policy and planning model. Mailbox
mutation must remain disabled until the execution controls required by REQ-004
and REQ-008 are satisfied.

## Core filing rule

For a mailbox covered by this requirement:

1. a message outside `INBOX` is not considered by normal Inbox filing;
2. an unread message in `INBOX` is left unchanged;
3. a read (`\\Seen`) message in `INBOX` becomes eligible for classification;
4. an eligible message is moved only when its disposition is to file and a safe
   canonical destination has been resolved;
5. a decision to Ignore leaves the message in `INBOX` and is not a move;
6. a decision to Junk marks the message for Thunderbird's junk filter and is
   not a move to a folder;
7. an ambiguous or unresolved message remains in `INBOX` and is presented for
   review.

Reading a message is therefore the user's signal that the message may be filed,
not a command to delete or archive it immediately.

## Mailbox scope

### Personal mailboxes

The initial filing workflow applies to the personal mailboxes:

- Andy current -> canonical taxonomy from `myMail`;
- Kathy -> canonical taxonomy from `kathyMail`.

The two personal archive taxonomies remain independent. A filing decision for
Andy does not silently create or alter a Kathy filing decision, and vice versa.

### Legacy mailbox

The legacy Andy mailbox may reuse Andy's canonical filing rules when REQ-004
migration planning applies. Its destination still follows the live-year and
legacy-target policy from REQ-004.

### Shared and support mailboxes

Shared and support mailboxes are excluded from this automatic personal Inbox
filing rule until a separate role-specific filing policy is defined.

## Filing identity

mailAgent groups related automated/business senders by domain while retaining the
exact sender address as evidence.

For example:

```text
billing@bmw.com       -> bmw.com
service@paypal.com    -> paypal.com
orders@amazon.co.uk   -> amazon.co.uk
```

Domain grouping must use the registrable/organisation domain rather than blindly
using only the last two labels. Country-code domains such as `amazon.co.uk` must
therefore remain intact.

Exact sender overrides may be supported where one address from a domain needs a
different destination from the normal domain destination.

## Canonical destination model

A filing destination is a canonical archive path such as:

```text
Cars/BMW
Finance/PayPal
Shopping/Amazon
```

The first component is the **Parent** category and the final component is the
business/domain folder.

### Parent discovery

mailAgent must discover available parents from the existing local archive for the
personal mailbox:

- discover top-level canonical folders from `myMail` for Andy;
- discover top-level canonical folders from `kathyMail` for Kathy;
- do not treat deeper descendants as additional parents;
- preserve the existing folder spelling/capitalisation;
- keep the discovered parent sets mailbox-specific.

For example, `Shopping/Amazon/Orders` contributes `Shopping` as an available
parent, not `Amazon` or `Orders`.

### Adding a parent

The user may propose a new parent when no existing category is appropriate.

- the UI must offer an `Add parent...` action;
- the proposed parent name must be validated and normalised consistently with
  the archive taxonomy;
- proposing a parent records a filing decision only;
- planning must not create the Thunderbird/local folder immediately;
- the plan must clearly distinguish an existing parent from a proposed parent.

### Child/domain folder

When a domain does not already map to an existing canonical folder, mailAgent may
suggest a user-readable child name derived from the sender/domain, for example:

```text
bmw.com       -> BMW
paypal.com    -> PayPal
amazon.co.uk  -> Amazon
```

The user can edit the proposed child name before approval.

## Filing decision precedence

For an eligible read Inbox message, destination resolution should use this order:

1. explicit exact-sender filing override, if one exists;
2. explicit domain-to-canonical-folder mapping for that mailbox;
3. an existing canonical archive-history classification when sufficiently safe;
4. otherwise unresolved/review.

A user decision always wins over an inferred classification. Ignore and Junk
are user decisions. Either one supersedes a folder mapping and archive-history
classification for that same sender or domain.

The plan must retain the reason/evidence for an inferred destination so the user
can understand why it was selected.

## Dispositions

A filing decision has one disposition:

- **File** — use a canonical parent/child path, as described above;
- **Ignore** — leave the messages in the Inbox. Do not propose a folder move
  and do not delete them;
- **Junk** — mark the messages as junk so Thunderbird's junk filter can
  recognise them. Do not file them into the personal archive, do not move them
  to a folder, and do not delete them.

Ignore and Junk have no canonical folder path. A folder path is stored only
for a File disposition.

Junk is a mark, not a mailAgent move. mailAgent must not create a Thunderbird
filter to express it. When execution is later permitted, the mark must be one
Thunderbird's own junk filter already uses. Thunderbird account settings may
still move mail after they see that mark; that move is Thunderbird's, not a
mailAgent filing action.

Phase 1 records Ignore and Junk and shows them as status. It does not change
message flags, junk state, or mailbox contents.

## Moving Mail

**Moving Mail** is a tab on the Mailbox Audit main menu. It is not a sub-panel
of Inbox Digest.

The view is domain-oriented and shows at least:

- mailbox/archive (`myMail` or `kathyMail`);
- domain;
- number of current Inbox messages represented;
- discovered or selected Parent, when the disposition is File;
- child/domain folder name, when the disposition is File;
- resulting canonical destination, when the disposition is File;
- status: `Existing`, `Proposed child`, `Proposed parent + child`,
  `Needs choice`, `Ignore`, or `Junk`.

A representative view is:

```text
Domain          Archive    Parent     Folder    Status
amazon.co.uk    myMail     Shopping   Amazon    Existing
bmw.com         myMail     Cars       BMW       Proposed child
nhs.uk          myMail     Medical    NHS       Proposed parent + child
news.example    myMail                          Ignore
offers.example  kathyMail                       Junk
```

The user must be able to select an existing discovered parent or propose a new
one without changing mail during that interaction. Choosing Ignore or Junk
does not ask for a folder and does not change mail during that interaction.

## Persistence

Filing decisions must be durable and separate from credentials and transient
scan state.

Store them under the mailAgent configuration area, using a dedicated schema such
as:

`~/.config/mailAgent/filing-rules.json`

The persisted model must support, at minimum:

- mailbox-specific domain mappings;
- optional mailbox-specific exact-sender overrides;
- the disposition (`file`, `ignore`, or `junk`);
- proposed/new parent metadata where the disposition is File;
- canonical destination path where the disposition is File;
- schema versioning and validation.

Persistence must be atomic, user-only, and contain no passwords or message
bodies.

## Filing plan

A read Inbox scan must produce structured filing proposals rather than directly
mutating mail.

Each proposal must include enough information to identify and audit the action,
including:

- source mailbox;
- source folder (`INBOX`);
- stable message identity such as UID and UIDVALIDITY;
- read/unread state used for eligibility;
- sender and domain;
- disposition (`file`, `ignore`, or `junk`);
- resolved canonical destination when the disposition is File;
- destination kind (`imap` or `local`) when the disposition is File;
- filing decision source (`sender`, `domain`, `archive history`, or equivalent);
- whether destination folder creation is required;
- whether execution is currently permitted.

Unread Inbox messages must not appear as filing actions. Ignore is not a move
proposal. Junk is not a move proposal; it records the junk mark to apply later.

## Destination and live-year behaviour

Filing must continue to respect REQ-004.

### Live-year mail

For current/live-year personal mail, the canonical destination is the matching
IMAP mirror folder where available or approved for creation.

A future execution step may move the read Inbox message from `INBOX` to that IMAP
folder once the destination is approved.

### Older mail

For pre-live-year mail, the destination is the corresponding local archive path
under `myMail` or `kathyMail`.

A future execution step must use copy -> verify -> remove semantics before the
server copy may be removed. A failed or unverified copy leaves the source message
untouched.

## Relationship with Thunderbird filters

mailAgent is the source of truth for filing rules introduced by this requirement.
It must not require equivalent Thunderbird filters to exist.

Existing Thunderbird filters must continue to be discovered and shown because
they may move messages before mailAgent evaluates the Inbox.

mailAgent must not automatically create Thunderbird filters as part of Inbox
filing. A separate future migration/reconciliation feature may convert useful
legacy Thunderbird filters into mailAgent filing rules or identify conflicts.

## Safety

- unread Inbox mail is never moved by this workflow;
- read mail with no resolved destination is never moved;
- Ignore leaves the message in `INBOX` and never deletes it;
- Junk does not file the message into the personal archive and never deletes it;
- normal filing never deletes a message;
- folder creation is explicit and reviewable;
- local archival uses copy -> verify -> remove;
- shared/support mailbox content is not subjected to personal filing rules;
- every executed filing action must be logged and auditable;
- repeated runs must be idempotent and must not duplicate archived messages.

## Acceptance criteria

- unread messages in `INBOX` remain untouched;
- read messages in `INBOX` become filing candidates;
- messages outside `INBOX` are not selected by normal Inbox filing;
- Andy and Kathy use their own local archive taxonomies;
- available Parent choices are discovered from the first level of the relevant
  local archive;
- a user can propose a new Parent without immediately creating a folder;
- senders can be grouped by registrable domain;
- domain mappings persist and are reused for subsequent senders/messages from
  that domain;
- an exact sender override can supersede a domain rule when needed;
- a resolved live-year message targets the canonical IMAP mirror;
- a resolved older message targets the canonical local archive;
- unresolved or ambiguous messages remain in Inbox and appear for review;
- **Moving Mail** is a main-menu tab, and Inbox Digest does not contain it;
- Ignore produces no folder proposal and leaves the messages in `INBOX`;
- Junk produces no archive-folder proposal and records a junk mark for
  Thunderbird's junk filter;
- neither Ignore nor Junk deletes mail or creates a Thunderbird filter;
- existing Thunderbird filters are discovered but new filters are not required
  or automatically created;
- planning makes no mailbox or local archive mutations;
- future execution cannot remove an IMAP source until any required local copy has
  been verified;
- all filing decisions and executed actions are traceable.

## Delivery phases

### Phase 1 - filing policy and review

- discover parents from `myMail` and `kathyMail`;
- group Inbox senders by domain;
- create/edit durable sender/domain filing mappings;
- support proposed parents and child folders;
- show Moving Mail status in the TUI, including Ignore and Junk;
- produce read-only filing proposals;
- record Ignore and Junk without changing flags or mail.

### Phase 2 - safe execution

- identify read Inbox messages eligible for filing;
- create approved destination folders where required;
- move live-year messages within IMAP only when the disposition is File;
- archive older messages using copy -> verify -> remove only when the
  disposition is File;
- leave Ignore messages in `INBOX`;
- mark Junk messages so Thunderbird's junk filter can use them, without
  filing those messages into the personal archive;
- log successful actions and retain retry-safe state.

Phase 2 must not be enabled merely by completing Phase 1.

## Change history

- 2026-10-08: Moving Mail is a main-menu tab rather than an Inbox Digest
  Filing sub-panel. Ignore leaves read Inbox mail in the Inbox. Junk marks it
  for Thunderbird's junk filter instead of filing it to a folder.
