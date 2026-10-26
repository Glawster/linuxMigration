# Release notes

Releases of this repository, newest first. The process is in
[Versioning and releases](../.github/additional-instructions.md#versioning-and-releases).

## Unreleased

- Versioning ([ADR 009](../project/adr/009-branchVersions.md)): every branch
  of work is numbered as an alpha of the next release (`1.4a1`, `1.4a2`, ...)
  and its merge into `main` is tagged with that number. New `branchVersion`
  tool: `show`, `start` (number the current branch) and `tag` (tag the merged
  work), previewing unless `--confirm` is given. Tool headers show a branch's
  own number, for example `1.4a3 (v1.4a2-1-g1a2b3c4)`.
- `hardwareSnapshot` is `1.4a1`; the `currentIncrement.md` update (#109) is
  `1.4a2`; this change is `1.4a3`.
- `hardwareSnapshot` (new): records a machine's hardware configuration and
  temperatures, reports when the configuration changes between runs, and keeps
  a per-host temperature history with disks identified by serial number
  ([guide](../linuxBootstrap/documentation/hardwareSnapshot.md)). It shows the
  repository version at start-up and with `--version`, and runs `smartctl` and
  `dmidecode` with `sudo -n` so it never waits for a password.
- `migrateToRaid`: copies are readable by other users such as Plex, whatever
  the source permissions (`permissions`, default `Dgo+rx,Fgo+r`), and a
  private folder already on raid-pc is corrected by the next copy through it.
- `bootstrap.sh`: setting a Media Center Master drive letter also removes
  Wine's raw-device reservation for that letter (`<letter>::`). A stale
  reservation let Wine take the letter back for whichever USB disk now has that
  device name, replacing or dropping the configured mapping.
- `migrateToRaid`: `copiedFiles` and `copiedBytes` count the files rsync
  logged as copied (its log now records each file's size), instead of rsync's
  summary, which counts every listed file when rsync stops on an error.
- `suggestUnwatched` (new, requirement 004): suggests the oldest unwatched
  shows from Plex watch state and Media Center Master air dates, with an
  exemption chooser and a reviewable `removeShows.sh`. It logs the repository
  version at start-up.
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
