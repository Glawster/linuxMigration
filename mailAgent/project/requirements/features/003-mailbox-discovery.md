# REQ-003 - Existing mailbox and filter discovery

## Purpose

Audit the existing mail environment before mailAgent makes organisation
decisions.

## Functional requirements

1. Discover the folder hierarchy independently for every configured IMAP
   mailbox.
2. Record IMAP folder attributes and special-use flags where available.
3. Record folder message and unread counts where practical.
4. Read IMAP quota information where supported.
5. Locate the active Thunderbird profile on the local Linux machine without
   assuming a fixed profile directory name.
6. Locate per-account `msgFilterRules.dat` files.
7. Parse existing Thunderbird filters in read-only mode.
8. Link filter target folders to discovered IMAP folders where possible.
9. Report unresolved filter destinations rather than discarding them.
10. Identify potential overlaps between existing filters and future mailAgent
    classification/organisation behaviour.
11. Persist a timestamped, secret-free discovery snapshot.
12. Compare the current snapshot with the previous snapshot.
13. Present folder, filter, conflict, quota and change information in the TUI.
14. Perform no mailbox or Thunderbird configuration mutation.

## Safety requirements

- IMAP folders must be opened/read in non-mutating mode.
- Thunderbird filter files must never be edited by this increment.
- Authentication secrets must never be written to discovery snapshots.
- An unknown filter syntax must be reported, not rewritten.
- No folder should be classified as safe to remove merely because it appears
  unused.

## Acceptance criteria

Given three configured mailboxes:

- all three are displayed in the Mailbox Audit TUI;
- the folder tree can be inspected independently for each mailbox;
- special folders are identified where the server reports them;
- existing Thunderbird filters can be viewed by account;
- filter target folders are linked to existing folders when resolvable;
- missing filter targets are visibly reported;
- quota is shown when supported and marked unavailable when unsupported;
- a discovery snapshot is written beneath
  `~/.local/state/mailAgent/discovery/`;
- a second discovery run can report structural/filter changes;
- no IMAP write operation or Thunderbird filter modification occurs.
