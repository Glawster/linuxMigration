# Release notes

Releases of this repository, newest first. The process is in
[Versioning and releases](../.github/additional-instructions.md#versioning-and-releases).

## Unreleased

- `bootstrap.sh`: previews no longer run wine. The Media Center Master check
  reads .NET 4.8 from the prefix's `system.reg`, so a preview never creates or
  upgrades `~/.wine-mcm`.
- `bootstrap.sh`: the DaVinci Resolve install folder can be overridden
  (`davinciRoot`), so its tests no longer depend on whether Resolve is
  installed.
- `scansnapToVM.py`: sets its logUtils application context before creating its
  logger, fixing a crash at startup with organiseMyProjects 0.9.
- Release process: tag only when all work is on `main` and every test suite
  passes.

## v1.3 (2026-10-24)

First tagged release. Introduces one repository version (`VERSION`, `vX.Y`
tags) and the `repoVersion.sh` and `repoVersion.py` helpers
([ADR 008](../project/adr/008-repositoryVersion.md)).

`migrateToRaid` ([guide](../linuxBootstrap/documentation/migrateToRaid.md)):

- Copy, verify, check and protection-gated removal of andy-pc storage on
  raid-pc or `/mnt/media` (requirement 001).
- Rebalancing `/mnt/movies` and `/mnt/video` to raid-pc through a recorded
  title plan (requirement 002, ADR 005).
- Running on raid-pc with the same configuration, reaching the pool locally
  (ADR 006).
- Newer artwork and metadata replace older copies instead of conflicting
  (ADR 007).
- A run header with the repository version, host, action and command line, and
  `--version`.
