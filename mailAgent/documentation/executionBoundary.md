# Execution boundary

[REQ-010](../project/requirements/features/010-approved-mailbox-change-execution.md)
starts with two core modules: `executionPlan` and `executionJournal`. Neither
imports Textual or IMAP clients. They do not create archive folders, write
messages, move mail, or change flags. The normal CLI and audit UI do not call
them. Execution remains disabled.

## Approval envelope

`executionPlanPrepare(filingPlan, config)` projects a schema-1 filing plan into
an execution envelope. Use normalized configuration from `configValidate`.
The envelope contains `schemaVersion`, `configFingerprint`, `executionEnabled`
and `entries`. Preparation always sets execution and entry approval to false.
It does not infer permission from a sender rule, domain rule, inferred
classification, or the CLI's `--confirm` preference.

A future approval workflow must explicitly set all three gates:

- envelope `executionEnabled=True`;
- entry `approved=True`;
- entry `executionPermitted=True`.

Folder creation requires the independent `folderCreationApproved=True` fact.
After recording the exact choices, approval must bind the entry to its immutable
identity with:

```python
entry["actionId"] = executionActionId(
    dict(entry, configFingerprint=envelope["configFingerprint"])
)
```

The ID includes mailbox, source folder, UIDVALIDITY, UID, disposition, year,
decision source, exact destination, creation permission and configuration
fingerprint. Transient destination existence is not part of the ID. These
hashes detect changed approval content; they are not digital signatures or a
replacement for a trusted user approval workflow.

The configuration fingerprint binds account IDs to host, port, username and
role, plus archive paths, folder mappings, live year and the configured junk
keyword. Credential values and credential references are excluded. Journal
actions contain only projected execution identity, never sender headers,
message bodies, credentials or arbitrary plan evidence.

## Revalidation

`executionPlanBuild(approved, config, current, completedActionIds)` returns
`actions`, `blocked` entries with indexes/reasons, and completed IDs to skip.
Its result still has `executionEnabled=False`: building it is not an Execute
operation. One blocked entry does not prevent independent valid entries from
being selected. Unsupported envelopes or changed configuration reject the
whole plan. A blocked entry includes its sanitized action when its approval
passed validation, so it can be registered and durably marked blocked without
starting an attempt. Malformed or unapproved entries supply only an index/reason.

`current` must be prepared from a newly rebuilt filing plan after fresh,
complete read-only discovery using the current configuration and filing rules.
Do not reuse the approval snapshot as the current observation. This module
accepts observations and performs no network queries itself. A future engine
must also probe source identity and eligibility immediately before mutation;
a successful validation result must not be cached as permanent permission.

The validator rejects missing or changed UIDs/UIDVALIDITY, unread or non-Inbox
sources, changed classification/destination/year, duplicate or conflicting
source entries, unapproved folder creation, cross-mailbox execution and
non-personal accounts. Legacy actions remain blocked in this first increment.
IMAP File requires the live year; local File requires an older year, an explicit
absolute destination inside the configured archive, and Thunderbird format.
A proposed local folder without a resolved storage path is blocked.

Ignore and Junk have no destination. Junk requires an explicit account
`junkKeyword` token; no keyword is guessed. This field is an execution-boundary
input, not a server capability check. A future IMAP primitive must establish
that the account supports the configured Thunderbird-compatible mechanism
before applying it.

Destination creation is idempotent at the validation boundary: a missing
approved folder may now exist at the exact same destination. A destination
that disappears is blocked unless creation was explicitly approved.

## Durable journal

`executionJournalRegister(actions)` stores validated action identities under
`~/.local/state/mailAgent/execution.sqlite3`, with schema version 1 and user-only
permissions. SQLite transactions serialize writers and atomically register a
batch. Full synchronous durability commits state before a future primitive runs.
Repeated registration preserves existing progress. A new ID for the same source
is rejected, including after completion; changed destinations require explicit
reconciliation rather than another copy.

The lifecycle is:

1. Register an action as `pending`, without a start timestamp.
2. Freshly validate it, then call `executionJournalStart(..., revalidated=True)`.
   The journal commits the start timestamp and attempt count before returning.
3. Record `completed`, `blocked`, or `failed` with `executionJournalFinish`.
   A blocked precondition can be recorded before starting.
4. On restart, a started pending action remains pending and has
   `requiresVerification=True`. It cannot be started again directly.
5. To retry an interrupted, blocked or failed action, first revalidate and
   reconcile any partial outcome. Only then call `executionJournalRetry` with
   both `revalidated=True` and `partialOutcomeVerified=True`.

Those booleans assert work performed by the future engine and read-only probes;
the journal does not perform the checks itself. There is no automatic retry or
state reset. A completed action is immutable and is skipped using
`executionJournalCompleted`. Unknown schemas, corrupt records, publicly readable
journal files and symlink journal paths fail closed.

Completion requires a matching verification result code:

| Action | Required result |
| --- | --- |
| IMAP File | `destination-verified` |
| Local File | `local-archive-and-removal-verified` |
| Ignore | `ignore-honoured` |
| Junk | `junk-state-verified` |

These codes record a future primitive's verified result; this increment does
not verify messages itself. Local-copy verification alone cannot complete the
whole archival action. The future engine must record source-removal outcome
only after a verified local copy, and preserve intermediate proof before any
removal. The IMAP primitive must verify both the intended destination message
and the source outcome before reporting the filing action complete.

The journal retains ordered attempt history, start/finish timestamps, status,
verification and fixed error codes. Use `executionJournalHistory` to read the
history. Arbitrary exception messages are not accepted as persisted error text.

## Next increment

Implement small fake-tested IMAP folder-creation and one live-year File
primitive, including partial-outcome reconciliation. Local archive writes,
junk marking, orchestration and the TUI Execute screen remain later steps.
