# REQ-006 - Inbox interest and daily digest

## Purpose

Allow the user to define what kinds of Inbox messages belong in a daily digest
without changing mailbox content.

The digest model has three layers:

1. reason policies that define which classes of messages are normally included;
2. sender-specific digest overrides;
3. sender-specific Person classification overrides.

mailAgent may classify likely digest reasons from lightweight Inbox headers, but
classification remains advisory and transparent.

## Interaction

The Mailbox Audit TUI includes an **Inbox Digest** view with two sub-panels:

- **Senders** - current Inbox senders and their effective digest inclusion;
- **Include Reasons** - the user's policy for each digest reason.

### Senders

Each sender row shows:

- mailbox identity;
- normalized sender email address;
- number of current Inbox messages from that sender;
- the reason inferred by mailAgent, when one exists;
- effective digest status;
- a sender-specific Digest setting;
- a sender-specific Person setting.

Do not show example subjects in the sender table. The view is intended to focus
on sender addresses per mailbox rather than exposing message text unnecessarily.

The **Digest** setting has three values:

- `Auto` - follow the classified reason policy;
- `In` - always include this sender;
- `Out` - always exclude this sender, even when its reason is `In`.

The **Person** setting has three values:

- `Auto` - use mailAgent's Person classification;
- `Yes` - treat this sender as a person when no more specific subject reason is
  present;
- `No` - do not classify this sender as Person.

Both settings are edited directly in the table. The user clicks/selects the
setting cell and presses left/right arrow to move between the available values.
Changes are persisted immediately; there is no separate Apply button.

The interaction changes only mailAgent preferences. It must not move, flag,
delete, mark read, or otherwise mutate any email.

### Include Reasons

The **Include Reasons** sub-panel lists every digest reason and lets the user set
one of three policies:

- `In` - messages classified with this reason are automatically included;
- `Out` - messages are not included by this reason unless a sender-specific
  Digest override is `In`;
- `Manual` - the reason alone never includes the message; a sender-specific
  Digest override is required.

The setting is edited directly in the table. The user clicks/selects the
Setting cell and presses left/right arrow to move through `Out`, `Manual` and
`In`. The change is saved immediately.

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

A sender-specific Person `No` corrects a false positive. Person `Yes` corrects a
false negative. Subject-specific reasons such as `Delivery` still take
precedence over Person classification.

## Persistence

Digest preferences are stored separately from mailbox credentials in:

`~/.config/mailAgent/interesting.json`

The file:

- uses schema version 1;
- may store reason policies in `reasonPolicies`;
- may store sender-specific Auto/In/Out choices in `senderPolicies`;
- may store sender-specific Auto/Yes/No Person choices in `personPolicies`;
- remains backward compatible with an existing schema-1 `mailboxes` sender list;
- is written atomically;
- is created with user-only permissions;
- contains no passwords or message bodies.

Reason classification itself is not stored as a decision; it is recalculated
from current Inbox headers plus any Person override.

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

1. sender Digest `In` or `Out`, if explicitly set;
2. otherwise the policy of the classified reason;
3. otherwise not included.

Digest generation, delivery time, formatting, and read/unread handling remain
separate future work.

## Acceptance criteria

- Inbox Digest contains separate **Senders** and **Include Reasons** sub-panels;
- reason settings are changed directly with left/right arrows;
- sender Digest settings are changed directly with left/right arrows;
- sender Person settings are changed directly with left/right arrows;
- reason and sender changes are saved immediately without a separate Apply step;
- the user can force a sender Out even when Person or another reason is In;
- the user can correct Person false positives with `No` and false negatives with
  `Yes`;
- Person and Reminder default to In;
- Delivery, Dispatch, Order, Payment and Invoice default to Out;
- subject-specific reasons take precedence over Person;
- sender and reason choices persist across TUI sessions;
- sender matching is mailbox-specific and case-insensitive;
- no email state changes when a preference is changed;
- the TUI remains usable when no Inbox headers are available;
- malformed preference storage is reported without modifying mail.
