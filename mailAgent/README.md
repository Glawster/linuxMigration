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
- [REQ-003](project/requirements/features/003-mailbox-discovery.md)
- [REQ-004](project/requirements/features/004-archive-taxonomy-migration.md)

## Install

    mkdir -p ~/bin
    cp -a mailAgent ~/bin/mailAgent
    cd ~/bin/mailAgent

    conda env create -f environment.yml
    conda activate mailAgent
    python -m pip install -e .

    mkdir -p ~/.config/mailAgent
    cp config.example.toml ~/.config/mailAgent/config.toml

Passwords are supplied via environment variables, not stored in the config:

    export MAILAGENT_ANDY_PASSWORD='...'
    export MAILAGENT_KATHY_PASSWORD='...'
    export MAILAGENT_OLD_PASSWORD='...'

Run with:

    mailAgent

Use `mailAgent --confirm` to persist the audit snapshot, or `--json` for
noninteractive output. Mailbox operations remain read-only.

The first version never deletes, moves, flags, or sends mail.

## Archive and migration planning

Set each mailbox host and password environment variable in
`config.toml`. Personal mailboxes also need `localArchive` pointing at an
existing archive directory. The existing archive hierarchy defines the taxonomy.
Use [config.example.toml](config.example.toml) for the required role settings.

    mailAgent --plan
    mailAgent --plan --json
    mailAgent --plan --confirm --json

`--plan` reads Date headers for personal/legacy messages and shows Mapping,
Proposed Moves, Review Queue and Role Boundaries panels. `--confirm` only saves
the audit and plan under `~/.local/state/mailAgent/discovery/`.
Migration execution remains disabled. Shared and support accounts remain
visible in the audit and produce no personal archive proposals.

## Discovery before organisation

Before mailAgent changes any mailbox structure, it performs a read-only audit
of the existing IMAP folders and local Thunderbird message filters. The agent
must work with the existing layout and identify existing rules before proposing
new organisation.

- [Discovery phase](documentation/discoveryPhase.md)
- [REQ-003 - Existing mailbox and filter discovery](project/requirements/features/003-mailbox-discovery.md)
