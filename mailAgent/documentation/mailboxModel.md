# Mailbox Model

## Initial mailboxes

| ID | Mailbox | Role | Archive behaviour |
| --- | --- | --- | --- |
| `andy` | `andyw@glawster.com` | personal | Current year on IMAP; older mail in `myMail` |
| `kathy` | `kathyw@glawster.com` | personal | Current year on IMAP; older mail in `kathyMail` |
| `old` | `andy@glawster.com` | legacy | Migration source into Andy current/local archive |
| `hwfc` | `info@hillsboroughwalkingfootball.com` | shared | Shared server taxonomy; no personal archive assumptions |
| `clannEolas` | `info@clanneolas.com` | support | Access/read/support only; excluded from archive migration |

## Mailbox roles

### personal

A normal personal mailbox.

- current live year remains on IMAP;
- older mail is archived locally;
- the local archive is the canonical filing taxonomy;
- applicable IMAP folders mirror that taxonomy for the live year.

### legacy

A source mailbox being retired or reduced.

For `andy@glawster.com`:

```text
2026 mail
    -> proposed migration to matching location in andyw@glawster.com

pre-2026 mail
    -> proposed migration to matching location in local myMail
```

No source mail is removed until the destination has been verified and the user
has confirmed the operation.

### shared

A mailbox actively used by multiple people.

`info@hillsboroughwalkingfootball.com` is shared.

Rules:

- preserve a server-side structure that makes sense to every mailbox user;
- do not mirror Andy's or Kathy's personal archive taxonomy into it;
- discovery should identify existing folders and filters before proposing
  changes;
- moves and folder creation must be reviewable;
- avoid user-specific filing rules that would make mail difficult for other
  mailbox users to locate;
- local archival, if introduced later, requires a separate shared-mailbox
  retention policy.

### support

A mailbox the user wants mailAgent to access for support/work purposes but not
manage as part of the archive migration system.

`info@clanneolas.com` is a support mailbox.

mailAgent may:

- read and search mail;
- highlight mail needing attention;
- classify messages for display;
- summarise threads;
- help draft responses;
- show unread/action status.

mailAgent must not, under REQ-004:

- mirror the personal local archive taxonomy;
- archive messages to `myMail` or another local personal archive;
- automatically move historical messages off the server;
- restructure its folder hierarchy;
- treat it as a legacy migration source.

Future requirements can add explicitly approved support-mailbox organisation.

## Live-year policy

The application has a configurable `liveYear`, initially:

```text
2026
```

For personal mailboxes:

```text
message year == liveYear
    -> IMAP

message year < liveYear
    -> local archive
```

This rule does not automatically apply to `shared` or `support` mailboxes.

## Configuration

Each mailbox declares its role explicitly.

Example:

```toml
[general]
liveYear = 2026

[[mailboxes]]
id = "andy"
name = "Andy"
username = "andyw@glawster.com"
role = "personal"
localArchive = "myMail"

[[mailboxes]]
id = "kathy"
name = "Kathy"
username = "kathyw@glawster.com"
role = "personal"
localArchive = "kathyMail"

[[mailboxes]]
id = "old"
name = "Old mailbox"
username = "andy@glawster.com"
role = "legacy"
localArchive = "myMail"
migrationTarget = "andy"

[[mailboxes]]
id = "hwfc"
name = "HWFC"
username = "info@hillsboroughwalkingfootball.com"
role = "shared"

[[mailboxes]]
id = "clannEolas"
name = "Clann Eolas"
username = "info@clanneolas.com"
role = "support"
```

Server host, port, and credential reference remain independently
configured for each mailbox.

## Implemented planning workflow

Use the Conda `mailAgent` environment and run:

```bash
mailAgent --plan
mailAgent --plan --json
mailAgent --plan --confirm --json
```

The first two commands preview; the third persists the audit and its migration
plan using REQ-003 snapshot history. `--confirm` permits snapshot persistence
only. Migration execution and folder creation are disabled in this increment.
No completed operations exist to record yet. A future executor must require
confirmation, copy and verify destinations before permitting source removal,
and persist completed operations separately from proposals.

Each mailbox requires `id`, `name`, `host`, `username`, `role` and either
`credentialId` or the compatibility `passwordEnv` reference. See
[encrypted credential setup](credentials.md).
Hosts and optional ports are independent. Personal mailboxes require
`localArchive`; legacy mailboxes require a `migrationTarget` naming a personal
mailbox and inherit its archive. If an explicit legacy archive is supplied, it
must match the target archive. Shared/support accounts reject personal archive,
mapping and migration settings. Existing REQ-003 configurations must add roles.
[The complete example](../config.example.toml) includes all five accounts.

`localArchive` points to an existing directory; `~` expands to the user's home
and relative paths resolve against the configuration file's directory. Missing
roots produce review issues and are never created. The default `archiveFormat`
is `thunderbird`: mbox files define selectable folders and sibling `.sbd`
directories define their descendants. For example, `Orders.sbd/Shop` becomes
canonical `Orders/Shop`, backed by that exact file. Empty mbox files are valid;
nonempty candidates must begin with an mbox `From ` separator. Metadata files
such as `.msf` indexes are excluded. Point at a `.sbd` directory if the archive
is a Thunderbird top-level folder with child folders. The top-level mbox itself
is not scanned when only its `.sbd` directory is configured.

`archiveFormat = "maildir"` supports nested directory layouts with `cur`, `new`
and `tmp` under each message store. It does not support flat Maildir++ dot-folder
layouts. Hidden files and symbolic links are excluded. Discovery does not open
Maildir message contents, and reads at most five bytes from each candidate mbox.
Unrecognized files and unreadable directories appear as review issues; incomplete
archive scans cannot supply message destinations.

Automatic mapping requires an exact canonical folder path, translated using
the server delimiter and IMAP modified UTF-7 encoding. A single observed server
delimiter permits missing-folder mirror proposals; ambiguous delimiters or
colliding destinations require review. Configure aliases explicitly per account:

```toml
folderMappings = { "INBOX.Orders" = "Orders" }
```

Keys are exact IMAP server paths; values are canonical paths present in that
personal archive. The legacy account may declare its own aliases, while the
personal target's aliases determine the live IMAP destination. Folder name
similarity and message subjects do not select a destination. Parent folders
without a message store cannot receive local archive proposals.

Planning uses the year in the message's single parsed Date header, as expressed
in that header's timezone, rather than server arrival year. Date headers are
fetched in UID batches through read-only EXAMINE and BODY.PEEK, without message
bodies or flag changes. UID and UIDVALIDITY identify source messages. Missing,
duplicate or invalid dates, future years, unmatched canonical folders and
special-use Trash/Junk/Drafts folders enter the Review Queue. A failed or
incomplete inventory yields no message proposals for that source mailbox.

A personal live-year message remains in its existing mapped IMAP folder. Older
mail proposes the matching local message store. Legacy live-year mail proposes
the personal target's matching IMAP folder, with folder creation explicitly
listed as a prerequisite if absent. Older legacy mail proposes that target's
local archive. All proposals are labelled Inferred and include confirmation
and verification prerequisites; they cannot authorize removing source copies.

The TUI presents Mapping, Proposed Moves, Review Queue and Role Boundaries
as read-only tables alongside the audit. Shared/support mailboxes remain visible
and audited, but `--plan` does not inventory their message headers or generate
personal folder mirrors, archive destinations or migration proposals.
