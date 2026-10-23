# Current Development Increment

## Increment

002 localMediaRebalance: rebalance local movies and TV to raid-pc

## Status

Active
<!-- Options: Active, Idle, Blocked, InReview -->

## Requirement

[project/requirements/features/002-localMediaRebalance.md](requirements/features/002-localMediaRebalance.md)

## Objective

Move the oldest movies and ended TV shows, as whole folders, from `/mnt/movies`
and `/mnt/video` to raid-pc until each disk is at most 50% occupied, without
splitting a show between stores.

## Scope

Rebalance planning in `linuxBootstrap/lib/raidMigrationPlan.sh`, its hooks in
`lib/raidMigration.sh` and `lib/raidMigrationStore.sh`, the configuration
template, tests and the migrateToRaid guide, on branch
`feature/localMediaRebalance` ([ADR 005](adr/005-rebalancePlan.md)).

## Verification

- [x] Automated tests for every acceptance criterion
      (`linuxBootstrap/tests/migrateToRaidTests.sh`)
- [x] Read-only preview of both plans against the real disks
- [ ] Review and merge `feature/localMediaRebalance`
- [ ] Finish the requirement 001 raid-pc migrations
- [ ] Move `linuxBackup` off `/mnt/video` to a retired USB disk
- [ ] Manual acceptance: review the real plans, then the first confirmed,
      fully verified rebalance and removal

## Next

Review the branch. The real rebalance waits for the requirement 001 migrations
to finish and for `linuxBackup` to leave `/mnt/video`.
