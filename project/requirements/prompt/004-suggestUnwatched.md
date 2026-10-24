# Prompt 004: implement suggestUnwatched

- Requirement: [004 Suggest unwatched video folders](../features/004-suggestUnwatched.md)
- Role: implement and test
- Decisions: [ADR 008](../../adr/008-repositoryVersion.md)

## Assignment

Implement `suggestUnwatched`, which suggests the oldest unwatched video folders
under a directory from Plex watch state and Media Center Master air dates, with
an exemption chooser and a reviewable removal script. Satisfy every acceptance
criterion in the requirement.

## Constraints

- Never move, delete or run the removal script.
- Read the Plex database only; never write to it.

## Component boundaries

- Implementation: `suggestUnwatched/src/suggestUnwatched/`.
- Tests: `suggestUnwatched/tests/`, run in the `suggestUnwatched` conda
  environment.
- Documentation: `suggestUnwatched/suggestUnwatchedIndex.md`,
  `suggestUnwatched/documentation/ranking.md`.
