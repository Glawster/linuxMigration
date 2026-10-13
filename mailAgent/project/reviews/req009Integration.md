# REQ-009 integration review

Reviewed on 2026-10-10 on `feature/010-approved-mailbox-change-execution`.

The tree at `origin/feature/009-read-inbox-filing` (`ab97f75`) is identical to
`f5f8ff2`, the squash already present on this branch. Merge `2a23aa9` records
that ancestry without replacing subsequent REQ-010, action-guidance or MA-011
work.

Phase 1 covers per-personal-mailbox taxonomy, read Inbox eligibility, domain
and exact sender decisions, proposed folders and Ignore/Junk planning. Existing
fake-mailbox tests cover unread exclusion, legacy reuse, role boundaries,
year routing, uncertain domains and sender precedence. Execution remains
separate under REQ-010.

The integration adds editable Parent with a retained dropdown, automatic domain
saving on Enter/focus change, and proposal of unfamiliar parents. Add parent,
Save domain and disposition dropdown controls are removed. Focused-table i/j
save Ignore/Junk and f opens destination editing. Input typing remains local;
The Sender override button is also removed: s in the table or Alt+s in the
editor reveals Sender; Enter saves the exact sender rule. Alt+i/j/f chooses
its disposition.

Focused UI checks cover selection/resize without writes, Enter and blur saves,
invalid-edit preservation, dropdown choices, new parent proposals, Junk-to-File
editing and exact sender overrides. Saving clears the selected row warning.
Plan refresh clears and restores action-needed classes as decisions change.

Rules loading now rejects symlinks, non-regular files, incorrect ownership or
non-owner-only permissions, boolean schema versions and invalid sender keys.
Atomic writes sync the temporary file and directory; interrupted writes before
replacement preserve the prior rule and clean the temporary file.

Phase 2 continues with one approved live-year File action: create an approved
IMAP destination when necessary, copy, verify destination, then remove source.
Retry safety must be proven before batches, local archive and Junk execution.
No live mailbox mutation was used for this integration review.

Validation: all 321 mailAgent tests passed. Black checks passed for changed
Python files and `git diff HEAD --check` reported no whitespace errors.
