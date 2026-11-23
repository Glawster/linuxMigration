# Release notes

Releases of this repository, newest first. The process is in
[Versioning and releases](../.github/additional-instructions.md#versioning-and-releases).

## Unreleased

- `pdfFiler` (requirement 005, `1.4a7`): suggests where each scanned PDF
  belongs and files it after one **File / Change… / Skip** dialog. It learns
  from the cabinet's names only (identifiers such as `AV2550339`, each
  folder's labels and types), from rules in `~/.config/pdfFiler/config.json`,
  and from reference numbers in PDFs you file. When two folders share a name,
  the rest of the path decides. Tax documents are dated at the end of the tax
  year and statements at the end of their period. Future dates and dates
  inside references are never used. New commands `pdfFiler.sh suggest` and
  `pdfFiler.sh index show`. It is now a Python project in `pdfFiler/`
  (ADRs 011 and 012); `pdfFiler.sh` is its launcher and keeps its `1.4a6`
  options ([guide](pdfFiler.md)).
- `pdfFiler.sh`: works again, and previews unless `--confirm` is given.
  It looks in `~/Documents/myCabinets` (the old path no longer existed) and
  reads the date from the PDF again (it read an unset variable). It
  understands written-out months such as `30 October 2026`, prefers labelled
  dates, and rejects dates that do not exist. It never overwrites a different
  file, sends a PDF already filed to the Trash, and picks up `.PDF` files. A
  declined PDF is no longer offered over and over. A year folder takes its
  parent's name (`... - Bank Statements - Statement.pdf`), and the preview
  window always closes. It no longer reuses the `TMPDIR` variable, which
  broke temporary files after the first PDF. It uses organiseMyProjects
  logging without an active conda environment and adds `--root`, `--inbox`
  and `--version`. This change is `1.4a6`
  ([guide](pdfFiler.md)).
- `fixDirectPaymentsStatements.sh`: files the Direct Payments timesheet
  spreadsheets into `myCabinets/Benefits/Statements` again; `1.4a4`'s
  follow-up commit had pointed it at `Benefits/Bank Statements`, the PDF
  bank statements folder. It also runs from a shell with no conda
  environment active: it finds organiseMyProjects' `logUtils.sh` through the
  active `python3`, then the `py312` environment (or `LOG_UTILS`), instead of
  exiting silently, and its fallback logger is gone, so a missing
  organiseMyProjects is a clear error. This change is `1.4a5`.
- `fileDpStatements` (new): files Direct Payments bank statements downloaded
  from the bank website, moving each from `~/Downloads` to
  `Bank Statements/<yyyy>/<yyyy-mm-dd> - Direct Payments - Statement - <Mon>.pdf`
  by the statement date on page 1. Previews unless `--confirm` is given;
  statements already filed under any name go to the Trash, and a different
  file under the target name is never overwritten
  ([guide](fileDpStatements.md)).
- Versioning ([ADR 009](../project/adr/009-branchVersions.md)): every branch
  of work is numbered as an alpha of the next release (`1.4a1`, `1.4a2`, ...)
  and its merge into `main` is tagged with that number. New `branchVersion`
  tool: `show`, `start` (number the current branch) and `tag` (tag the merged
  work), previewing unless `--confirm` is given. Tool headers show a branch's
  own number, for example `1.4a3 (v1.4a2-1-g1a2b3c4)`.
- `hardwareSnapshot` is `1.4a1`; the `currentIncrement.md` update (#109) is
  `1.4a2`; this change is `1.4a3`.
- `migrateToRaid`: movie and TV disks are safe to remove after a quick
  verification (every file's size and date), set per type by `removalVerify`
  (ADR 010); home video and pictures still need full checksums.
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
