# REQ-006 - Inbox interest and daily digest

## Purpose

Allow the user to define what kinds of Inbox messages belong in a daily digest
without changing mailbox content.

The digest model has two layers:

1. reason policies that define which classes of messages are normally included;
2. explicit sender includes that may override a reason policy.

mailAgent may classify likely digest reasons from lightweight Inbox headers, but
classification remains advisory and transparent.

## Interaction

The Mailbox Audit TUI includes an **Inbox Digest** view with two sub-panels:

- **Senders** - current Inbox senders and their effective digest inclusion;
- **Include Reasons** - the user's policy for each digest reason.

### Senders

Each sender row shows:

- whether the sender is currently included in the digest;
- mailbox identity;
- normalized sender email address;
- number of current Inbox messages from that sender;
- the reason inferred by mailAgent, when one exists;
- whether inclusion came from an explicit Sender choice or from the Reason
  policy.

Do not show example subjects in the sender table. The view is intended to focus
on sender addresses per mailbox rather than exposing message text unnecessarily.

The user moves to a sender row and presses `Space` to toggle an explicit sender
include. An explicit sender include wins over an `Out` or `Manual` reason policy.
Removing the explicit sender include returns the sender to its reason policy.

The Inbox Digest sender view shows `Space to Toggle Sender of interest`; this
hint must not appear on unrelated tabs.

The interaction changes only mailAgent preferences. It must not move, flag,
delete, mark read, or otherwise mutate any email.

### Include Reasons

The **Include Reasons** sub-panel lists every digest reason and lets the user set
one of three policies:

- `In` - messages classified with this reason are automatically included;
- `Out` - messages are not included by this reason, unless their sender has an
  explicit include;
- `Manual` - the reason alone never includes the message; explicit sender
  selection is required.

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
- stores normalized exact sender includes by mailbox ID;
- may store reason policies in an optional `reasonPolicies` mapping;
- remains backward compatible with an existing schema-1 file that contains only
  sender selections;
- is written atomically;
- is created with user-only permissions;
- contains no passwords or message bodies.

Reason classification itself is not stored as a decision; it is recalculated
from current Inbox headers.

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

1. explicit sender include, if present;
2. otherwise the policy of the classified reason;
3. otherwise Manual/not included.

Digest generation, delivery time, formatting, and read/unread handling remain
separate future work.

## Acceptance criteria

- Inbox Digest contains separate **Senders** and **Include Reasons** sub-panels;
- the user can set every known reason to In, Out or Manual;
- Person and Reminder default to In;
- Delivery, Dispatch, Order, Payment and Invoice default to Out;
- explicit sender inclusion overrides Out and Manual reason policies;
- removing an explicit sender include returns to the reason policy;
- a likely human sender can be classified as Person using From header metadata;
- obvious automated/service senders are not classified as Person;
- subject-specific reasons take precedence over Person;
- sender and reason choices persist across TUI sessions;
- sender matching is mailbox-specific and case-insensitive;
- no email state changes when a preference is changed;
- the TUI remains usable when no Inbox headers are available;
- malformed preference storage is reported without modifying mail.
