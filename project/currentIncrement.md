# Current Development Increment

## Increment

003 agentSessionsStandards

## Status

InReview

## Requirement

[003: Agent session listing standards](requirements/features/003-agentSessionsStandards.md)

## Objective and scope

Align agentSessions with .github coding standards while preserving read-only
session discovery. Scope includes the command, its tests, usage documentation
and requirement records on feature/agentSessions-process. No commits produced.
The previous raidMigration work remains governed by requirement 001 and its
existing feature/migrateToRaid branch; it is not completed by this increment.

## Acceptance and verification

- Criteria 1–5: synthetic stores for four agents, metadata fallback, latest/all/full,
  source preservation, malformed input, missing stores and I/O warnings verified.
- Criterion 6: 20 targeted tests pass. Black and targeted
  OMP lint pass, with an identical temporary .py copy of the extensionless command.
- Commands use PYTHONPATH=/home/andy/Source/organiseMyProjects because the default
  interpreter has no installed organiseMyProjects package.
- Wider `python -m pytest tests` fails during existing test_scansnapToVM collection:
  scansnapToVM calls getLogger before the shared application context is set.
- Criteria 7–8: agent grouping, newest-first ordering, numbered full-ID extraction
  and invalid-selector stderr/exit behaviour verified.
- Current-directory filtering, symlink identity, --all directory expansion and
  --history selection verified.
- Independent review and human acceptance remain required before completion/merge.

## Risks and suite impact

Provider formats remain existing local assumptions; malformed records can yield a
partial listing and I/O warnings should be reviewed. No requirement/ADR changes
proposed beyond requirement 003. OMS, OMV and OMP have no runtime changes.
OMPR is consumed through its existing logging API; its linter rejects extensionless
scripts, so an identical temporary .py file is used for review. No shared tooling
or managed conventions were changed.

## Next

Review requirement 003 and the implementation, perform human CLI acceptance in the
intended Python environment, then commit and merge through the normal process.
