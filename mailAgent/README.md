# mailAgent

A local TUI-first IMAP mail organiser designed to work alongside Thunderbird.

Initial release is read-only. It connects to multiple IMAP mailboxes and
classifies recent messages as:

- For Me
- Active Order
- Active Delivery
- Completed Order
- General

The supplied example configuration is designed for three mailboxes:

- Andy
- Kathy
- Old mailbox

## Intended location

    ~/bin/mailAgent

## Documentation

- [Storage and retention](documentation/storageRetention.md)
- [Storage requirement](project/requirements/features/002-storage-retention.md)

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

    mail-agent

The first version never deletes, moves, flags, or sends mail.

## Proposed order folders

    Orders/
    ├── Active
    └── Completed/
        ├── 2026
        ├── 2025
        └── ...

Delivery notifications remain active only while the order is still current.
Later versions can move completed order and delivery mail into the appropriate
year folder after review.


## Storage policy

The IMAP server is the authoritative store for live/current mail so that
Thunderbird and mailAgent see the same organisation. Older completed mail may
be archived locally in a standard mail format to control server quota usage.

Retention is configured per mailbox, allowing the Andy, Kathy, and old
mailboxes to use different policies. See
[`documentation/storageRetention.md`](documentation/storageRetention.md).


## Discovery before organisation

Before mailAgent changes any mailbox structure, it performs a read-only audit
of the existing IMAP folders and local Thunderbird message filters. The agent
must work with the existing layout and identify existing rules before proposing
new organisation.

- [Discovery phase](documentation/discoveryPhase.md)
- [REQ-003 - Existing mailbox and filter discovery](project/requirements/features/003-mailbox-discovery.md)
