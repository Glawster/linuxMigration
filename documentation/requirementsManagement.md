<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# Requirements management

This guide defines the shared OMP process for capturing, agreeing, delivering
and maintaining requirements.

## Core principles

- Describe the user or system outcome before proposing an implementation.
- Give every requirement a permanent three-digit identifier and stable path.
- Keep one authoritative requirement specification; link to it instead of
  copying it.
- Keep requirements small enough to implement and verify independently.
- Make scope, exclusions, acceptance criteria and verification explicit.
- Keep transient implementation status solely in
  `project/currentIncrement.md`.
- Use Git history for delivery history rather than rewriting completed records.
- `README.md` is reserved for the repository root.
- When a directory genuinely needs an index, derive its filename as
  `<folderName>Index.md`.

## Authoritative locations

```text
project/requirements/
├── requirementsIndex.md
├── features/
│   └── 003-viewManagement.md
├── prompt/
│   ├── 003-viewManagement.md
│   └── adapters/
└── templates/
    └── requirement.md
```

- `project/requirements/requirementsIndex.md` is the requirements index and
  next-ID authority.
- `project/requirements/features/` contains every requirement specification at
  every lifecycle stage.
- `project/requirements/prompt/` contains one or more flat prompt files per
  requirement plus optional shared support directories such as `adapters/`.
- `project/requirements/templates/` contains approved requirement templates.
- Significant decisions belong in `project/adr/` and are linked from affected
  requirements. Its index is `project/adr/adrIndex.md`.

Do not create a per-requirement or per-prompt directory merely to hold a
`README.md`, an index file, `prompt.md`, or one specification/prompt file.

## Requirement identification and naming

Allocate the next number from `project/requirements/requirementsIndex.md` and
create:

```text
project/requirements/features/nnn-requirementName.md
```

For example:

```text
project/requirements/features/003-viewManagement.md
```

Rules:

- `nnn` is a zero-padded three-digit sequential identifier.
- The identifier is permanent and never reused.
- `requirementName` is a concise camelCase name.
- The filename and identifier do not change when lifecycle status changes.
- Repository-specific prefixes may be used in external tools but are not part
  of the OMP filename.
- Individual requirements are named Markdown files, not directory indexes.

## Prompt naming

A requirement with one prompt uses the same filename under the prompt folder:

```text
project/requirements/features/003-viewManagement.md
project/requirements/prompt/003-viewManagement.md
```

When one requirement genuinely needs multiple prompts, append sequential
lowercase letters to the requirement number while keeping the same name:

```text
project/requirements/prompt/003a-viewManagement.md
project/requirements/prompt/003b-viewManagement.md
project/requirements/prompt/003c-viewManagement.md
```

Use the unsuffixed form only while there is one prompt. If a second prompt is
added later, rename the existing unsuffixed prompt to the `a` form, create `b`,
and update all references in the same change. Never reuse a prompt suffix.

A prompt assigns work; it does not redefine the requirement. The requirement
specification remains authoritative for outcome, scope and acceptance criteria.

## Requirement record

Each requirement should use at least:

```markdown
# 003: View management

## Status

ToDo

## Outcome

As a <user or system>, I need <capability> so that <measurable benefit>.

## Context

Why this is needed and the relevant constraints.

## Scope

- Behaviour included in this requirement.

## Out of scope

- Closely related behaviour deliberately excluded.

## Acceptance criteria

1. Given <starting condition>, when <action>, then <observable result>.

## Dependencies and decisions

- Related requirements, ADRs, external dependencies or `None`.

## Verification

- Planned tests, review steps or other evidence.

## Change history

- YYYY-MM-DD: created — reason or source.
```

Add measurable non-functional constraints only when they apply.

## Workflow

### 1. Capture

Search existing records for duplicates. Allocate the next number from
`requirementsIndex.md`, create the requirement and its primary prompt, add the
index row with `ToDo`, and record the requirement's origin.

### 2. Refine and agree

Review outcome, scope, exclusions, acceptance criteria, dependencies and
verification. Record consequential implementation choices as ADRs rather than
embedding their rationale in the requirement.

### 3. Start delivery

Set both the requirement record and its row in `requirementsIndex.md` to
`InProgress`. Record the active delivery state in
`project/currentIncrement.md`.

### 4. Implement

Keep implementation and tests within the agreed scope. Update durable product
or technical documentation when delivered behaviour changes. If the agreed
outcome changes materially, update the requirement through change control.

### 5. Verify and complete

Verify every acceptance criterion. Set both the requirement and its index row
to `Completed` only when the evidence is sufficient. Git commits, pull requests,
tags and releases remain the delivery history.

## Requirements index

`project/requirements/requirementsIndex.md` contains the traceability matrix
using these columns:

| Column | Purpose |
| --- | --- |
| `Req ID` | Permanent zero-padded identifier. |
| `Requirement` | Link to the authoritative requirement specification. |
| `Description` | Concise description. |
| `Status` | `ToDo`, `InProgress`, or `Completed`. |
| `Agent Prompt` | Link(s) to the durable prompt file(s). |
| `Architecture Decisions` | Supporting ADR links, `Pending`, or `Not required`. |

Example:

```markdown
# Requirements

Next available number: 006

| Req ID | Requirement | Description | Status | Agent Prompt | Architecture Decisions |
| --- | --- | --- | --- | --- | --- |
| 003 | [Manage views](features/003-viewManagement.md) | Create and manage saved views. | Completed | [Implement](prompt/003a-viewManagement.md), [verify](prompt/003b-viewManagement.md) | [ADR-002](../adr/002-viewStorage.md) |
| 004 | [Export parsed messages](features/004-exportParsedMessages.md) | Export parsed messages. | ToDo | [Prompt](prompt/004-exportParsedMessages.md) | Pending |
```

The index is navigation/status metadata, not a replacement for the individual
requirements.

## Requirements and ADRs

A requirement defines the outcome and acceptance evidence. An ADR records a
consequential implementation or project-shaping decision. ADR directory
navigation and local instructions use `project/adr/adrIndex.md`; individual
ADRs remain named numbered files.

One ADR may support several requirements and one requirement may depend on
several ADRs. Link both directions where useful; do not duplicate rationale.

## Prompt content and agent handoff

A prompt should identify:

- the requirement ID and path;
- the requested role (implement, test, review, document, etc.);
- assigned acceptance criteria;
- relevant exclusions, constraints and ADRs;
- allowed component/file boundaries;
- verification commands; and
- the expected handoff evidence.

Shared agent adapters may live under
`project/requirements/prompt/adapters/`. If that directory ever needs its own
index, the filename would be `adaptersIndex.md`; do not create one unless the
index has a real purpose.

## Change control

- Before implementation, refine the existing requirement in place.
- During implementation, change the record only when a durable obligation
  changes materially.
- After completion, create a new linked requirement for a new outcome rather
  than rewriting the original delivery.
- Never recycle identifiers or move completed requirements to an archive.

## OMP 0.6 legacy cleanup

`manageProject --update` may migrate only deterministic, no-loss legacy forms.
Recognised index migrations include:

```text
project/requirements/README.md
project/requirements/folderIndex.md
    -> project/requirements/requirementsIndex.md

project/adr/README.md
project/adr/folderIndex.md
    -> project/adr/adrIndex.md
```

`requirementsIndex.md` and `adrIndex.md` are the canonical destinations.

Recognised erroneous artifact forms include a single deterministic file such as:

```text
project/requirements/features/003-viewManagement/README.md
    -> project/requirements/features/003-viewManagement.md

project/requirements/prompt/003-viewManagement/README.md
    -> project/requirements/prompt/003-viewManagement.md
```

Cleanup rules:

- establish the exact artifact identity before changing anything;
- preserve user-owned or third-party nested READMEs;
- preserve directories containing additional/ambiguous content;
- never overwrite a different canonical destination automatically;
- remove a legacy directory only when it is empty after successful migration;
- dry-run reports intended changes without modifying files; and
- successful reruns are idempotent.

## Review checklist

Before `InProgress`:

- outcome, scope and exclusions are clear;
- acceptance criteria are testable;
- dependencies and decisions are linked;
- verification exists; and
- specification and `requirementsIndex.md` agree.

Before `Completed`:

- every criterion has evidence;
- tests cover relevant normal/boundary/failure behaviour;
- documentation and ADR links are current;
- no unresolved item is hidden by completion; and
- specification and `requirementsIndex.md` agree.
