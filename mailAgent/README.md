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
- [REQ-003](project/requirements/features/003-mailbox-discovery.md)
- [REQ-004](project/requirements/features/004-archive-taxonomy-migration.md)
- [REQ-005](project/requirements/features/005-encrypted-credentials-store.md)
- [REQ-006](project/requirements/features/006-inbox-interest-daily-digest.md)

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

The first version never deletes, moves, flags, or sends mail.

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

## Discovery before organisation

Before mailAgent changes any mailbox structure, it performs a read-only audit
of the existing IMAP folders and local Thunderbird message filters. The agent
must work with the existing layout and identify existing rules before proposing
new organisation.

- [Discovery phase](documentation/discoveryPhase.md)
- [REQ-003 - Existing mailbox and filter discovery](project/requirements/features/003-mailbox-discovery.md)

## Inbox interest

The normal Mailbox Audit TUI includes an **Inbox Interest** tab. It groups
current Inbox messages by sender. Select a sender and press `Space` to toggle
`✓ Interesting`.

Interesting senders are stored in
`~/.config/mailAgent/interesting.json` and are intended to drive a future
daily digest. Toggling the check mark changes only mailAgent preferences; it
does not alter email state.

Migration planning also learns conservative filing evidence from the existing
local archive. An exact sender historically filed in one canonical folder can
be used to classify otherwise-unmapped mail. If a sender address contains a
unique canonical folder name, such as `paypal` matching `Finance/PayPal`,
mailAgent may propose that folder with an explicit classification reason.
