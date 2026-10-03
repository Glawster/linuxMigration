# REQ-006 - Inbox interest and daily digest

## Purpose

Allow the user to mark Inbox senders as senders of interest in the TUI so mailAgent can
later include matching messages in a daily digest without changing mailbox
content.

## Interaction

The Mailbox Audit TUI includes an **Inbox Digest** view.

Each row represents one sender observed in an Inbox and shows:

- a check mark when the sender is marked as a sender of interest;
- mailbox identity;
- normalized sender email address;
- number of current Inbox messages from that sender;
- an example subject.

The user moves to a sender row and presses `Space` to toggle the check mark. The Inbox Digest view shows `Space to Toggle Sender of interest`; this hint must not appear on unrelated tabs.

A checked sender means:

> Messages from this exact sender are of interest to me and are candidates for
> the daily digest.

The interaction changes only mailAgent preferences. It must not move, flag,
delete, mark read, or otherwise mutate any email.

## Persistence

Interesting-sender preferences are stored separately from mailbox credentials in:

`~/.config/mailAgent/interesting.json`

The file:

- uses schema version 1;
- stores normalized exact sender addresses by mailbox ID;
- is written atomically;
- is created with user-only permissions;
- contains no passwords or message bodies.

## Inbox discovery

The interactive audit may fetch lightweight Inbox headers only:

- `Date`
- `From`
- `Subject`

It must use read-only IMAP access and `BODY.PEEK`. Message bodies are not
required for sender-interest selection.

## Daily digest

Checked senders define one source of future daily-digest content.

The first increment records and displays the preference only. Digest generation,
delivery time, formatting, and read/unread handling are separate future work.

## Acceptance criteria

- an Inbox sender can be marked and unmarked with `Space`;
- a checked sender displays `✓`;
- the choice persists across TUI sessions;
- sender matching is mailbox-specific and case-insensitive;
- no email state changes when the preference is toggled;
- the TUI remains usable when no Inbox headers are available;
- malformed preference storage is reported without modifying mail.
