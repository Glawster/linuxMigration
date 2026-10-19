# Requirements

Requirement records for linuxMigration, following
[requirements management](../../documentation/requirementsManagement.md).

Next available number: 002

| Req ID | Requirement | Description | Status | Agent Prompt | Architecture Decisions |
| --- | --- | --- | --- | --- | --- |
| 001 | [raid-pc storage migration](features/001-raidMigration.md) | Copy, verify and record migration of andy-pc storage to raid-pc or the local `/mnt/media` disk; protection-gated safe disk removal. | InProgress | [Implement](prompt/001-raidMigration.md) | [ADR 001](../adr/001-raidMigrationSafety.md), [ADR 002](../adr/002-localMigrationDestination.md), [ADR 003](../adr/003-migrateOnRaidPc.md) |
