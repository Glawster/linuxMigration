# Prompt 001: implement raid-pc storage migration

- Requirement: [001 raid-pc storage migration](../features/001-raidMigration.md)
- Role: implement and test
- Decisions: [ADR 001](../../adr/001-raidMigrationSafety.md)

## Assignment

Implement `migrateToRaid`, which migrates andy-pc storage to raid-pc as
COPY → VERIFY → RECORD, with source removal as a separate explicit operation.
Satisfy every acceptance criterion in the requirement.

## Constraints

- Safety first: never `mv` across machines, never `--delete` during the copy,
  never overwrite a differing destination file, and never delete source data
  unless `--check` would report SAFE.
- Follow the repository CLI convention: preview by default, `-y`/`--confirm`
  to act, no `--dry-run`. Deletion needs a typed confirmation or
  `--yes-delete`.
- Keep mappings in configuration. Do not assume raid-pc destination paths or
  the number of raid-pc disks.
- Treat COPY VERIFIED and SAFE TO REMOVE as distinct. SAFE needs a full
  verification of the current source and a passing, configurable raid-pc
  protection check.
- Never copy, modify or delete real `/mnt` sources or raid-pc storage during
  development or tests.
- Leave `linuxBootstrap/lib/remotePull.sh` and its users unchanged.

## Component boundaries

- Implementation: `linuxBootstrap/migrateToRaid.sh`,
  `linuxBootstrap/lib/raidMigration*.sh`, the `~/bin/migrateToRaid` launcher.
- Configuration template: `linuxBootstrap/configs/migrateToRaid/config.json`.
- Tests: `linuxBootstrap/tests/migrateToRaidTests.sh`, registered in
  `linuxBootstrap/tests/runTests.sh`.
- Documentation: `linuxBootstrap/documentation/migrateToRaid.md`, linked from
  the READMEs.

## Verification

```bash
./linuxBootstrap/tests/migrateToRaidTests.sh
./linuxBootstrap/tests/runTests.sh
```

## Handoff evidence

- Passing test output, with any failures that already exist on `main`
  identified.
- A summary of assumptions that need the owner's confirmation.
