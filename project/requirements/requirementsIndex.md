# Requirements

Requirement records for linuxMigration, following
[requirements management](../../documentation/requirementsManagement.md).

Next available number: 003

| Req ID | Requirement | Description | Status | Agent Prompt | Architecture Decisions |
| --- | --- | --- | --- | --- | --- |
| 001 | [raid-pc storage migration](features/001-raidMigration.md) | Copy, verify and record migration of andy-pc storage to raid-pc or the local `/mnt/media` disk; protection-gated safe disk removal. | InProgress | [Implement](prompt/001-raidMigration.md) | [ADR 001](../adr/001-raidMigrationSafety.md), [ADR 002](../adr/002-localMigrationDestination.md), [ADR 004](../adr/004-migrateOnlyOnAndyPc.md) |
| 002 | [Rebalance local movies and TV to raid-pc](features/002-localMediaRebalance.md) | Move the oldest movies and ended TV shows, as whole folders, from `/mnt/movies` and `/mnt/video` to raid-pc until each disk is at most 50% occupied. | InProgress | [Implement](prompt/002-localMediaRebalance.md) | [ADR 005](../adr/005-rebalancePlan.md) |
