# Architecture decisions

Consequential linuxMigration decisions, numbered `nnn-decisionName.md` and never
reused. Status values: Proposed, Accepted, Superseded (link the replacement).

Next available number: 009

| ADR | Title | Status | Requirements |
| --- | --- | --- | --- |
| [001](001-raidMigrationSafety.md) | Safety model for migrating storage to raid-pc | Accepted | [001](../requirements/features/001-raidMigration.md) |
| [002](002-localMigrationDestination.md) | Local destinations alongside raid-pc | Accepted | [001](../requirements/features/001-raidMigration.md) |
| [003](003-migrateOnRaidPc.md) | Migrating disks attached to raid-pc | Superseded by [004](004-migrateOnlyOnAndyPc.md) | [001](../requirements/features/001-raidMigration.md) |
| [004](004-migrateOnlyOnAndyPc.md) | migrateToRaid runs only on andy-pc | Superseded by [006](006-migrateOnHostWithDisk.md) | [001](../requirements/features/001-raidMigration.md) |
| [005](005-rebalancePlan.md) | Rebalancing through a recorded title plan | Accepted | [002](../requirements/features/002-localMediaRebalance.md) |
| [006](006-migrateOnHostWithDisk.md) | Migrating a disk on the machine it is attached to | Accepted | [001](../requirements/features/001-raidMigration.md) |
| [007](007-newerMetadataWins.md) | Newer artwork and metadata replace older copies | Accepted | [001](../requirements/features/001-raidMigration.md) |
| [008](008-repositoryVersion.md) | One version and release tag for the whole repository | Accepted, amended by [009](009-branchVersions.md) | — |
| [009](009-branchVersions.md) | A version number for every branch of work | Accepted | — |
