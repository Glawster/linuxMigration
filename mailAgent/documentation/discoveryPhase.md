# Discovery Phase

## Purpose

Before `mailAgent` proposes or performs any organisation, it must understand the
mail system that already exists.

Discovery is read-only. Its job is to observe:

- the current IMAP folder hierarchy for each configured mailbox;
- standard/special-use folders reported by the server;
- existing Thunderbird message filters;
- the relationships between filters and folders;
- existing order, delivery, archive, personal, and miscellaneous folders;
- mailbox quotas where the IMAP server exposes them.

The result is an auditable snapshot that subsequent requirements can use when
deciding how mail should be classified or moved.

## Mailboxes

The initial installation supports three independently configured mailboxes:

- Andy
- Kathy
- Old mailbox

Each mailbox is discovered separately. No assumption is made that they share
the same server, folder hierarchy, retention policy, or Thunderbird filters.

## IMAP discovery

For each mailbox the agent should collect, where available:

- account ID and display name;
- server host;
- folder path;
- folder delimiter;
- subscribed/unsubscribed state where supported;
- IMAP special-use attributes such as Inbox, Sent, Drafts, Junk and Trash;
- message count;
- unseen/unread count;
- child folders;
- quota usage and limit where supported.

The discovery phase must not create, rename, subscribe, unsubscribe, move, flag,
or delete anything.

## Existing folder interpretation

The agent should not force a predefined structure onto an existing mailbox.

It should identify likely purposes from folder names and context, for example:

- order/purchase folders;
- delivery/tracking folders;
- personal/important mail;
- archive folders;
- year-based folders;
- sender/vendor folders.

Interpretation is advisory. The original folder name and path remain the source
of truth.

The TUI should distinguish:

- **Observed** - facts directly reported by IMAP or Thunderbird;
- **Inferred** - a likely purpose proposed by mailAgent;
- **Conflict** - a folder or rule whose purpose is ambiguous or overlaps another
  rule.

## Thunderbird profile discovery

Thunderbird filters are local to the Thunderbird profile and are not assumed to
be discoverable from IMAP.

On Linux, profile discovery should begin with the Thunderbird profile metadata
beneath:

```text
~/.thunderbird/
```

Do not hard-code a particular profile name.

For each relevant account directory, look for the Thunderbird filter file:

```text
msgFilterRules.dat
```

Typical account locations include:

```text
<profile>/ImapMail/<account>/msgFilterRules.dat
<profile>/Mail/<account>/msgFilterRules.dat
```

Discovery must read these files only.

## Filter discovery

For each Thunderbird filter, capture:

- filter name;
- enabled/disabled state;
- filter type/trigger if available;
- conditions;
- actions;
- target folder paths;
- source account;
- raw source location.

The initial parser does not need to support editing.

If a filter cannot be parsed completely, retain the raw rule and report the
unsupported element rather than silently ignoring it.

## Filter/folder reconciliation

Discovery should identify:

1. filters whose target folders exist;
2. filters whose target folders cannot be found;
3. multiple filters targeting the same folder;
4. filters that appear to implement behaviour mailAgent was considering;
5. likely clashes between proposed agent behaviour and existing filters;
6. folders receiving messages but having no corresponding Thunderbird filter;
7. filters referring to folders that have been renamed or removed.

No automatic decision should be made from these findings.

## Discovery snapshot

Discovery output should be persisted beneath:

```text
~/.local/state/mailAgent/discovery/
```

The snapshot should be machine-readable and versioned, for example:

```text
discovery/
├── latest.json
└── history/
    └── discovery-YYYYMMDD-HHMMSS.json
```

The snapshot must not contain mailbox passwords or authentication secrets.

A snapshot records what was observed at one point in time so later scans can
show what changed.

## TUI - Mailbox Audit

The discovery increment should add a Mailbox Audit view.

Suggested layout:

```text
┌ Mailboxes ───────┐ ┌ Mailbox Audit ────────────────────────────────┐
│ Andy             │ │ Folders  Filters  Conflicts  Quota           │
│ Kathy            │ ├───────────────────────────────────────────────┤
│ Old              │ │ Inbox                         1,283 / 42 new  │
│                  │ │ Orders                                      │
│                  │ │   Amazon                                    │
│                  │ │ Archive                                     │
│                  │ │   2025                                      │
│                  │ │                                              │
│                  │ │ Selected: Orders/Amazon                       │
│                  │ │ Observed: normal IMAP folder                  │
│                  │ │ Inferred: order storage                       │
│                  │ │ Filters targeting folder: 2                   │
└──────────────────┘ └───────────────────────────────────────────────┘
```

The view should allow the user to inspect:

- Folder tree
- Filter list
- Folder/filter relationships
- Conflicts/warnings
- Quota information
- Changes since the previous discovery snapshot

## Safe-by-default behaviour

The discovery phase has no `--confirm` behaviour because it performs no mailbox
mutation.

If a shared CLI framework requires `--confirm`, accepting it must not enable any
write operation in this increment.

## Completion criteria

Discovery is complete when the user can review all three mailboxes in the TUI
and answer:

- What folders currently exist?
- Which folders are special/system folders?
- What Thunderbird filters currently exist?
- Which folders do those filters affect?
- Are there broken or ambiguous rules?
- Which existing rules already handle orders or delivery notifications?
- How much server space is in use, where available?
- What changed since the last audit?

## Running the implemented audit

The discovery package requires Python 3.11 or later (Conda Python 3.12 is
recommended), `organiseMyProjects`, and Textual. Configuration is TOML with
`[[mailboxes]]` entries containing `id`, `name`, `host`, `username`, and
`credentialId` (or compatibility `passwordEnv`); `port` defaults to 993. Every mailbox must now declare an
explicit `role`; see [Mailbox model](mailboxModel.md). Authentication uses IMAP over TLS with
the [encrypted credential store](credentials.md), or an environment-variable
password when no credential ID is configured. No predecessor application code was present
when this increment was implemented.

Run `mailAgent` for an audit preview. Run `mailAgent --confirm` to persist
`latest.json` and a unique historical snapshot. The shared safe-by-default CLI
convention applies to snapshot writes; neither command changes mail or
Thunderbird. `mailAgent --json` provides noninteractive output. Overrides are
available through `--config`, `--thunderbird`, and `--state`.

The version-1 snapshot records mailbox identities, folders, quota resources,
Thunderbird sources and raw rules, destination relationships, conflicts and
changes. Passwords and configuration authentication fields are excluded.
Raw rules may contain private subjects or addresses, so snapshots remain local.
Folder paths preserve IMAP wire spelling (including modified UTF-7), delimiter,
and attributes. Counts use STATUS; no message bodies are fetched. Quota STORAGE
units are KiB; other resources retain counts. Subscriptions are not queried.

Thunderbird `profiles.ini` and `installs.ini` identify default profiles. All
metadata-listed profiles are audited and default profiles are labelled; the
metadata cannot prove which running instance is active. Account identity is
read from `prefs.js` directory, hostname and username preferences. IMAP and POP
filter files are inspected. Only exact IMAP URI account and folder matches are
resolved; local POP targets, aliases and encoding mismatches remain warnings.

Filter conditions retain their original expression rather than executing it.
Unknown fields, malformed lines, custom actions and unsupported condition
syntax retain their raw source and produce issues. Duplicate rule names are
compared by occurrence within their source. Failed mailbox scans do not report
folders as removed. Missing Thunderbird sources currently appear as removed
filters; review profile availability before interpreting those changes.

The TUI provides mailbox tabs and scrollable Folders, Filters, Conflicts, Quota
and Changes panels. Facts are labelled Observed, category heuristics Inferred,
and unresolved or shared destinations Warning/Conflict. Heuristics use names
and conditions and do not modify classification rules.
