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
template, tests and the migrateToRaid guide
([ADR 005](adr/005-rebalancePlan.md)). Merged to `main` in #97; a later planning
fix is on `feature/replaceableMediaVerify`.

## Verification

- [x] Automated tests for every acceptance criterion
      (`linuxBootstrap/tests/migrateToRaidTests.sh`)
- [x] Read-only preview of both plans against the real disks
- [x] Review and merge `feature/localMediaRebalance` (#97)
- [x] Copy and verify the requirement 001 raid-pc migrations; `myPicturesMovies`
      has no recorded source removal
- [x] Retire `linuxBackup` from `/mnt/video`: replaced by snapshot backups and
      deleted
- [ ] Manual acceptance: review the real plans, then the first confirmed,
      fully verified rebalance and removal

## Next

The real rebalance started on 2026-11-03, targeting 41% on `/mnt/video` and 50%
on `/mnt/movies`. TV is copied and verified, and movies is copying. When movies
has verified, run `snapraid sync` on raid-pc, then check and remove the source
of each mapping to complete manual acceptance.
