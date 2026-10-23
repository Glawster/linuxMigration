# 003: Agent session listing standards

## Status

InProgress

## Outcome

As a local CLI user, I need agentSessions to follow repository development
standards so that session discovery remains maintainable, observable and safe.

## Context

The existing standalone script lists Codex, Claude, Grok and Copilot sessions.
Its root location is consistent with this repository's PATH-based utilities.

## Scope

- Show latest sessions for the current directory by default; --all includes all directories.
- Use --history for older sessions and --full for complete IDs.
- Group rows by agent, newest first, and provide numbered full-ID extraction.
- Apply shared logging, domainAction naming, types and focused helpers.
- Handle missing stores, malformed records and I/O failures without editing sessions.
- Add automated acceptance evidence and a maintained usage guide.

## Out of scope

Session resumption, deletion, agent-format redesign, packaging the repository,
and changes to unrelated utilities or managed guidance.

## Acceptance criteria

1. Representative stores for all four agents yield the correct agent, ID and directory.
2. Default listing selects the latest session per agent for the exact resolved cwd; --all includes all directories, --history includes older sessions and --full shows full IDs.
3. Missing stores and malformed JSON do not crash discovery; I/O failures produce contextual warnings.
4. Session data remains unchanged; only shared application logs are written.
5. The CLI exposes help, version, verbose and quiet options and initialises shared logging at entry.
6. Production-path tests, Black and targeted OMP lint pass; verification limitations are reported.

7. Rows are grouped alphabetically by agent, newest first within each group; numbered selectors match this ordering.
8. --id ROW prints only the selected full resume ID to stdout; invalid selectors fail with status 2 and a stderr error.

## Dependencies and decisions

- organiseMyProjects.logUtils is required; no fallback logging or runtime installation.
- No ADR required: existing standalone utility architecture is retained.

## Verification

- tests/test_agentSessions.py: real parsers, synthetic on-disk stores, CLI subprocesses and shared logging.
- Black check and targeted OMP linter; use an identical temporary .py copy for the extensionless executable.
- Independent review and human acceptance before completion/merge.

## Change history

- 2026-10-23: created from the request to align agentSessions with .github coding process.
- 2026-10-23: added agent grouping and numbered resume-ID extraction at user request.
- 2026-10-23: default to cwd; --all expands directories and --history includes older sessions.
