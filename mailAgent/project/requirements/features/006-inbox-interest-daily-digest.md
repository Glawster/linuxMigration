# REQ-006 - Inbox interest and daily digest

## Purpose

Allow the user to define what kinds of Inbox messages belong in a daily digest
without changing mailbox content.

The digest model has two layers:

1. reason policies that define which classes of messages are normally included;
2. explicit sender includes/excludes that may override a reason policy.

mailAgent may classify likely digest reasons from lightweight Inbox headers, but
classification remains advisory and transparent.

## Interaction

The Mailbox Audit TUI includes an **Inbox Digest** view with two sub-panels:

- **Senders** - current Inbox senders and their effective digest inclusion;
- **Include Reasons** - the user's policy for each digest reason.

### Direction convention

Editable digest choices use one consistent direction throughout the TUI:

- **Left** moves toward the positive choice (`In` or `Yes`);
- **Right** moves toward the negative choice (`Out` or `No`).

Where a neutral state exists it sits between those choices:

- digest sender: `In <- Auto -> Out`;
- person classification: `Yes <- Auto -> No`;
- reason policy: `In <- Manual -> Out`.

Changes are saved immediately.

### Senders

Each sender row shows:

- mailbox identity;
- normalized sender email address;
- number of current Inbox messages from that sender;
- the reason inferred by mailAgent, when one exists;
- effective digest inclusion;
- explicit Digest policy (`Auto`, `In`, `Out`);
- explicit Person policy (`Auto`, `Yes`, `No`).

Do not show example subjects in the sender table. The view is intended to focus
on sender addresses per mailbox rather than exposing message text unnecessarily.

The user may click the **Digest** or **Person** setting and use Left/Right to edit
it. In addition, when the sender email-address cell is selected, single-key
shortcuts are available:

- `i` - Digest = In;
- `o` - Digest = Out;
- `a` - Digest = Auto;
- `y` - Person = Yes;
- `n` - Person = No.

An explicit Digest `In` or `Out` wins over the reason policy. `Auto` returns the
sender to the normal reason-policy decision.

An explicit Person `Yes` or `No` corrects mailAgent's sender classification.
`Auto` returns classification to mailAgent's heuristic. Person Auto remains
editable with Left/Right on the Person cell.

The interaction changes only mailAgent preferences. It must not move, flag,
delete, mark read, or otherwise mutate any email.

### Include Reasons

The **Include Reasons** sub-panel lists every digest reason and lets the user set
one of three policies:

- `In` - messages classified with this reason are automatically included;
- `Out` - messages are not included by this reason unless their sender has an
  explicit Digest In override;
- `Manual` - the reason alone never includes the message; an explicit sender
  choice is required.

Initial defaults are:

- `Person` - In;
- `Reminder` - In;
- `Delivery` - Out;
- `Dispatch` - Out;
- `Order` - Out;
- `Payment` - Out;
- `Invoice` - Out;
- `Action required`, `Appointment`, `Booking`, `Renewal`, `Security` and
  `Verification` - Manual.

These defaults reflect that operational notifications are often useful but not
necessarily personally relevant enough for a daily digest.

## Classification reasons

Subject-based reasons may include:

- action required;
- appointment;
- booking;
- delivery;
- dispatch;
- invoice;
- order;
- payment;
- reminder;
- renewal;
- security;
- verification.

mailAgent may also classify a sender as `Person` when the From header contains a
credible personal display name and the sender address does not look like an
automated/service mailbox. Person detection must be conservative. It must not
classify obvious no-reply, newsletter, notification, billing, support, service,
customer-service or similar operational addresses as people merely because a
From display name is present.

When a message matches a specific subject reason such as `Delivery`, that reason
takes precedence over the generic `Person` classification.

## Persistence

Digest preferences are stored separately from mailbox credentials in:

`~/.config/mailAgent/interesting.json`

The file:

- uses schema version 1;
- stores normalized exact sender policies by mailbox ID;
- stores optional Person overrides by mailbox ID and sender;
- may store reason policies in an optional `reasonPolicies` mapping;
- remains backward compatible with an existing schema-1 file containing the old
  sender-selection list;
- is written atomically;
- is created with user-only permissions;
- contains no passwords or message bodies.

`Auto` is represented by the absence of a sender/person override where possible;
`In`, `Out`, `Yes` and `No` are durable explicit choices. Reason policies are
also durable.

Reason classification itself is not stored as a decision; it is recalculated
from current Inbox headers and then adjusted by any Person override.

## Inbox discovery

The interactive audit may fetch lightweight Inbox headers only:

- `Date`
- `From`
- `Subject`

mailAgent may retain the decoded From display name alongside the normalized
address solely for digest classification and presentation logic.

It must use read-only IMAP access and `BODY.PEEK`. Message bodies are not
required for sender-interest selection or classification.

## Daily digest

Effective sender inclusion is determined by:

1. explicit sender Digest policy, if In or Out;
2. otherwise the policy of the classified reason;
3. otherwise Manual/not included.

Digest generation, delivery time, formatting, and read/unread handling remain
separate future work.

## Acceptance criteria

- Inbox Digest contains separate **Senders** and **Include Reasons** sub-panels;
- the user can set every known reason to In, Out or Manual;
- Left consistently moves toward In/Yes and Right toward Out/No;
- sender email selection supports `i`, `o`, `a`, `y` and `n` shortcuts;
- Person and Reminder default to In;
- Delivery, Dispatch, Order, Payment and Invoice default to Out;
- explicit sender In/Out overrides the reason policy;
- Auto returns the sender to the reason policy;
- a user can correct Person false positives and false negatives with No/Yes;
- a likely human sender can be classified as Person using From header metadata;
- obvious automated/service senders are not classified as Person;
- subject-specific reasons take precedence over Person;
- sender, person and reason choices persist across TUI sessions;
- sender matching is mailbox-specific and case-insensitive;
- no email state changes when a preference is changed;
- the TUI remains usable when no Inbox headers are available;
- malformed preference storage is reported without modifying mail.
