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

Server host, port, and password environment variable remain independently
configured for each mailbox.
