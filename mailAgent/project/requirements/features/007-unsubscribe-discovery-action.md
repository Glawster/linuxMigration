# REQ-007 - Unsubscribe discovery and action

## Purpose

Identify unsubscribe information in email so the user can review and act on
mailing-list and marketing subscriptions from mailAgent.

## Functional requirements

1. Inspect unsubscribe metadata without changing message state.
2. Prefer standards-based headers where present:
   - `List-Unsubscribe`;
   - `List-Unsubscribe-Post` for one-click unsubscribe.
3. Recognise both HTTPS and `mailto:` unsubscribe mechanisms.
4. Where standards-based headers are absent, optionally inspect rendered/body
   content for explicit unsubscribe links or actions.
5. Record the source of the unsubscribe evidence so the UI can distinguish:
   - standards-based header;
   - one-click unsubscribe;
   - unsubscribe link found in message content;
   - mailto unsubscribe.
6. Associate unsubscribe information with the sender and mailbox.
7. Present unsubscribe-capable senders/messages in a user-facing TUI view or
   action associated with Inbox review.
8. Do not automatically unsubscribe.
9. Require an explicit user action before opening or submitting an unsubscribe
   request.
10. For one-click requests, show the user what will be sent before execution.
11. Never follow arbitrary links merely because they contain the word
    `unsubscribe`; only present links discovered from the message itself.
12. Preserve the existing read-only audit behaviour until the user explicitly
    chooses an unsubscribe action.

## Safety requirements

- Discovery must use `BODY.PEEK` or equivalent non-mutating access.
- Do not mark messages read while looking for unsubscribe metadata.
- Do not execute HTTP requests or send unsubscribe mail during discovery.
- Treat unsubscribe URLs and mailto targets as untrusted external content.
- Do not expose authentication credentials or unrelated message body content in
  logs or snapshots.
- An unsubscribe action must be attributable to a specific mailbox, sender and
  message.

## Acceptance criteria

- mail with a valid `List-Unsubscribe` header is identified;
- RFC-style one-click unsubscribe is distinguished from a normal link;
- `mailto:` unsubscribe is identified;
- an explicit unsubscribe link in message content can be surfaced when no
  header is available;
- the user can see the sender and available unsubscribe method before acting;
- discovery alone sends no email, makes no HTTP request and changes no IMAP
  state;
- no unsubscribe request occurs without an explicit user action.
