# Codex Prompt - REQ-003 Existing mailbox and filter discovery

Implement REQ-003 for `mailAgent`.

Read and follow the repository's OMP-managed instructions before changing code,
especially:

- `AGENTS.md`
- `.github/agent-instructions.md`
- `.github/repositoryLayout.md`
- `.github/requirementsManagement.md`
- `.github/additional-instructions.md`
- `project/requirements/features/003-mailbox-discovery.md`
- `documentation/discoveryPhase.md`

## Scope

Implement only the read-only discovery increment.

### IMAP

For each configured mailbox:

- connect using the existing configuration/authentication mechanism;
- enumerate folders using IMAP;
- preserve the server's folder delimiter and raw folder path;
- record standard/special-use attributes where available;
- capture useful message/unread counts without downloading all message bodies;
- query quota when the server supports it;
- do not create, rename, move, flag, subscribe/unsubscribe or delete anything.

Keep IMAP discovery in core/business modules independent of Textual.

### Thunderbird

On Linux:

- discover Thunderbird profiles beneath `~/.thunderbird`;
- identify the relevant active/default profile using Thunderbird metadata where
  possible rather than choosing an arbitrary directory;
- locate account directories in `ImapMail` and `Mail`;
- locate and read `msgFilterRules.dat`;
- build a parser that extracts filter name, enabled state, conditions, actions
  and destination folders;
- preserve raw/unparsed content when syntax is unsupported;
- never write the Thunderbird profile.

Do not require Thunderbird to be stopped because this increment is read-only.

### Reconciliation

Build a core model connecting:

```text
Mailbox -> Folder
Mailbox -> Thunderbird account/filter source
Filter -> Conditions
Filter -> Actions
Filter move/copy target -> Folder
```

Report:

- resolved destinations;
- unresolved destinations;
- multiple filters using the same destination;
- likely order/delivery-related existing filters;
- likely overlaps with mailAgent's existing classification categories.

Do not automatically alter agent rules because of an overlap.

### Persistent discovery snapshot

Store secret-free snapshots under:

```text
~/.local/state/mailAgent/discovery/
```

Use a versioned JSON schema.

Maintain:

```text
latest.json
history/discovery-<timestamp>.json
```

Implement comparison against the previous snapshot for at least:

- folder added/removed;
- filter added/removed;
- filter enabled-state change;
- filter destination change.

### TUI

Add a Mailbox Audit view with navigation for:

- Folders
- Filters
- Conflicts
- Quota
- Changes

The UI is orchestration/presentation only. It must not contain parsing,
discovery, reconciliation or comparison business logic.

Clearly label values as:

- Observed
- Inferred
- Warning/Conflict

### OMP requirements

- Conda remains the preferred environment.
- Core functions follow the project's OMP naming conventions.
- Use `organiseMyProjects.logUtils`.
- Add/update tests.
- Use `tmp_path` for filesystem tests.
- Mock IMAP responses rather than requiring a real mail server in automated
  tests.
- Do not auto-install dependencies.
- Run Black and the OMP linter.
- Keep the change safe-by-default.

## Tests

At minimum cover:

1. IMAP LIST parsing.
2. Folder delimiters and nested folders.
3. Special-use folder attributes.
4. Servers without quota support.
5. Quota response parsing.
6. Thunderbird profile discovery.
7. Multiple Thunderbird profiles.
8. IMAP and POP account filter-file discovery.
9. Valid `msgFilterRules.dat` parsing.
10. Disabled filters.
11. Move/copy destination parsing.
12. Unsupported filter syntax retained as an issue.
13. Missing target folder reconciliation.
14. Existing target folder reconciliation.
15. Discovery snapshot contains no passwords.
16. Snapshot comparison.
17. Core discovery imports no Textual modules.

## Completion

Provide:

- implementation;
- tests;
- documentation updates if implementation reveals necessary clarifications;
- a concise summary of what was discovered/implemented;
- commands used to test and lint;
- any unsupported Thunderbird filter constructs encountered.

Do not implement message moves, archive operations, filter editing, automatic
classification actions, or sending mail in this increment.
