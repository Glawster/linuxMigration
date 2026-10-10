# mailAgent

A local TUI-first IMAP mail organiser designed to work alongside Thunderbird.

The application audits IMAP folders and Thunderbird filters and builds
role-aware archive/migration proposals in read-only mode.
Future classification categories are:

- For Me
- Active Order
- Active Delivery
- Completed Order
- General

The example configuration declares five independent mailboxes: Andy and Kathy
(personal), Old (legacy), HWFC (shared), and Clann Eolas (support).

## Intended location

    ~/bin/mailAgent

## Documentation

- [Discovery phase and usage](documentation/discoveryPhase.md)
- [Mailbox roles and migration planning](documentation/mailboxModel.md)
- [Encrypted credentials setup](documentation/credentials.md)
- [MA-011 Login-session password cache](project/requirements/features/MA-011-sessionCredentialCache.md)
- [REQ-003](project/requirements/features/003-mailbox-discovery.md)
- [REQ-004](project/requirements/features/004-archive-taxonomy-migration.md)
- [REQ-005](project/requirements/features/005-encrypted-credentials-store.md)
- [REQ-006](project/requirements/features/006-inbox-interest-daily-digest.md)
- [REQ-007](project/requirements/features/007-unsubscribe-discovery-action.md)
- [REQ-008](project/requirements/features/008-plan-resolution-approval.md)
- [REQ-009](project/requirements/features/009-read-inbox-filing.md)
- [Inbox filing](documentation/inboxFiling.md)
- [Requirements](project/requirements/requirementsIndex.md)
- [Execution boundary](documentation/executionBoundary.md)
- [REQ-010](project/requirements/features/010-approved-mailbox-change-execution.md)

## Install

    mkdir -p ~/bin
    cp -a mailAgent ~/bin/mailAgent
    cd ~/bin/mailAgent

    conda env create -f environment.yml
    conda activate mailAgent
    python -m pip install -e .

    mkdir -p ~/.config/mailAgent
    cp config.example.toml ~/.config/mailAgent/config.toml

Create the GPG-encrypted store at `~/.config/mailAgent/credentials.json.gpg`
using the [credentials setup guide](documentation/credentials.md). Each mailbox
selects an entry with `credentialId`; passwords stay out of `config.toml`.
GPG must be installed separately and able to unlock the store through its agent
or pinentry. Existing `passwordEnv` configurations remain supported temporarily.

Run with:

    mailAgent

Use `mailAgent --confirm` to persist the audit snapshot. JSON is an optional
machine-readable export and is always written to a file rather than stdout.
Mailbox operations remain read-only.

Normal CLI/TUI workflows never delete, move, flag, or send mail. REQ-010 now
provides a separately invoked, fake-tested core API for one approved IMAP File
action; see [Execution boundary](documentation/executionBoundary.md).

## Archive and migration planning

Set each mailbox host and credential ID in
`config.toml`. Personal mailboxes also need `localArchive` pointing at an
existing archive directory. The existing archive hierarchy defines the taxonomy.
Use [config.example.toml](config.example.toml) for the required role settings.

    mailAgent --plan
    mailAgent --plan --json
    mailAgent --plan --json ~/Documents/mail-plan.json
    mailAgent --plan --confirm --json

`--plan` reads Date/From headers for personal/legacy messages, writes the concise
human-readable summary through `organiseMyProjects.logUtils`, and opens the TUI
with a **Plan** tab containing the same readable summary. With `--json`, the TUI
is not opened and the structured result is written to file.

`--json` also writes the complete structured result to
`~/.local/state/mailAgent/discovery/plan.json`. Supplying a path after
`--json` writes there instead. JSON is not printed to the terminal.

`--confirm` only saves the audit and plan baseline under
`~/.local/state/mailAgent/discovery/`. Migration execution remains disabled.
Shared and support accounts remain excluded from personal archive proposals.


### Planning from the TUI

The **Plan** tab is always visible. The most recent plan is stored automatically
at `~/.local/state/mailAgent/discovery/latest-plan.json` and reused on the next
normal TUI launch. The Plan tab uses a `Refresh Plan` button to create or
refresh the plan. Activating the button closes the current audit
view, runs a fresh read-only planning scan, and reopens the TUI with the plan
populated. Once a plan exists, the Plan summary shows when it was generated and
offers `Refresh Plan` to perform a fresh read-only rescan and
replace the stored plan.

Planning detail uses a second-level menu inside **Plan**: Summary, Mapping,
Proposed Moves, Review Queue and Role Boundaries. Mapping hides filesystem
storage paths. Proposed Moves shows the sender instead of IMAP UID values and
renders destination hierarchy with `/` separators for readability.

The button does not enable migration execution or persist a snapshot.


The TUI does not expose a dedicated quota tab. IMAP quota data may still be discovered internally and can be surfaced later as a warning if it becomes operationally relevant.

## Discovery before organisation

Before mailAgent changes any mailbox structure, it performs a read-only audit
of the existing IMAP folders and local Thunderbird message filters. The agent
must work with the existing layout and identify existing rules before proposing
new organisation.

- [Discovery phase](documentation/discoveryPhase.md)
- [REQ-003 - Existing mailbox and filter discovery](project/requirements/features/003-mailbox-discovery.md)

## Inbox Digest

The normal Mailbox Audit TUI includes an **Inbox Digest** tab. It groups
current Inbox messages by sender. Select a sender and press `Space` to toggle
`✓ Sender of interest`.

Interesting senders are stored in
`~/.config/mailAgent/interesting.json` and are intended to drive a future
daily digest. Toggling the check mark changes only mailAgent preferences; it
does not alter email state.

Migration planning also learns conservative filing evidence from the existing
local archive. An exact sender historically filed in one canonical folder can
be used to classify otherwise-unmapped mail. If a sender address contains a
unique canonical folder name, such as `paypal` matching `Finance/PayPal`,
mailAgent may propose that folder with an explicit classification reason.


## Folder view

The **Folders** view combines the live IMAP folder hierarchy with configured
personal local archives. IMAP rows are labelled `IMAP`; local archive rows are
labelled by archive name, such as `myMail` or `kathyMail`. This gives one
place to see both the live and long-term stores without exposing filesystem
paths.


## Plan resolution

The next planning phase is governed by
[REQ-008](project/requirements/features/008-plan-resolution-approval.md).

The first increment allows an unresolved sender in **Plan > Review Queue** to be
assigned to an existing canonical archive folder. Select the review row, choose
the canonical folder and use **Use folder for selected sender**. mailAgent stores
the mailbox-specific decision in
`~/.config/mailAgent/plan-resolution.json`, then refreshes the read-only plan.

The decision applies to subsequent messages from that sender in the same source
mailbox and is identified in proposals as an explicit user sender decision.
Saving a resolution never moves or modifies mail.

## Inbox filing

Read Inbox mail can be matched to the personal archive taxonomy. Unread Inbox
mail stays in the Inbox. Andy and Kathy keep separate rules, stored in
`~/.config/mailAgent/filing-rules.json`.

The **Moving Mail** tab groups the current Inbox by registrable domain. When
the Public Suffix List does not identify one organisation domain, the panel
asks you to confirm it. You can choose or propose a parent folder.
**Ignore** leaves that mail in the Inbox. **Junk** marks it for Thunderbird's
junk filter instead of filing it to a folder in a future execution phase.
Both choices can be saved now without choosing a folder.
Saving a rule or proposing a parent does not create folders, move mail, mark
junk, or create Thunderbird filters. Filing execution remains disabled. See
[Inbox filing](documentation/inboxFiling.md).

Sent/system-folder policy decisions and approval of demand-driven IMAP mirror
folders remain the following increments of REQ-008. Migration execution remains
disabled.
