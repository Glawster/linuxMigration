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
13. Present IMAP folders and configured local archive folders together in the TUI, clearly identifying the store for each row.
14. Present filter, conflict and change information in the TUI.
15. Keep quota discovery available internally; do not require a dedicated quota TUI view.
16. Perform no mailbox or Thunderbird configuration mutation.

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
- the folder view shows IMAP folders for each mailbox and the configured personal local archives such as `myMail` and `kathyMail`;
- each folder row identifies whether it belongs to IMAP or a local archive;
- special folders are identified where the server reports them;
- existing Thunderbird filters can be viewed by account;
- filter target folders are linked to existing folders when resolvable;
- missing filter targets are visibly reported;
- a discovery snapshot is written beneath
  `~/.local/state/mailAgent/discovery/`;
- a second discovery run can report structural/filter changes;
- no IMAP write operation or Thunderbird filter modification occurs.


## Conflict presentation refinement

The Conflicts view must be user-facing rather than exposing Thunderbird storage
internals.

- Show the mailbox, Thunderbird filter name, status, problem and friendly
  destination folder.
- Keep raw filter-file paths and numeric rule identifiers in diagnostic data
  only.
- Collapse exact duplicate conflict rows in the TUI.
- Distinguish advisory inferred overlaps from actual warnings.
- Do not mutate or disable Thunderbird filters from this view.
