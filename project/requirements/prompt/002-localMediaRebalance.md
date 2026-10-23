# Prompt 002: implement the local movies and TV rebalance

- Requirement: [002 Rebalance local movies and TV to raid-pc](../features/002-localMediaRebalance.md)
- Role: implement and test
- Decisions: [ADR 001](../../adr/001-raidMigrationSafety.md), [ADR 004](../../adr/004-migrateOnlyOnAndyPc.md), [ADR 005](../../adr/005-rebalancePlan.md)

## Assignment

Add a rebalance plan to `migrateToRaid` that selects whole movie and ended-show
folders, oldest first, from `/mnt/movies/Movies` and `/mnt/video/TV` until each
disk is at most 50% occupied, and moves them through the existing
COPY → VERIFY → RECORD pipeline with explicit removal. Satisfy every
acceptance criterion in the requirement.

## Constraints

- Never split a show: select, copy, verify and remove whole show folders only.
- Shows not marked `Ended` in `series.xml`, or without one, are never selected.
- Only `TV` is eligible on `/mnt/video`.
- Keep every requirement 001 safety rule and ADR 001: preview by default,
  `--confirm` to act, no `--dry-run`, never overwrite a differing destination
  file, and remove only verified, unchanged, selected folders after a SAFE
  check.
- Never copy, modify or delete real `/mnt` sources or raid-pc storage during
  development or tests.

## Component boundaries

- Implementation: `linuxBootstrap/migrateToRaid.sh`,
  `linuxBootstrap/lib/raidMigration*.sh` (planning in
  `lib/raidMigrationPlan.sh`).
- Configuration template: `linuxBootstrap/configs/migrateToRaid/config.json`.
- Tests: `linuxBootstrap/tests/migrateToRaidTests.sh`.
- Documentation: `linuxBootstrap/documentation/migrateToRaid.md`.
