# 007: Newer artwork and metadata replace older copies

- Status: Accepted
- Date: 2026-10-24
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)
- Related: [ADR 001](001-raidMigrationSafety.md)
- Amends: [ADR 001](001-raidMigrationSafety.md) decision 1

## Context

ADR 001 records every destination file that differs from the source as a
conflict, never overwritten, and a mapping with conflicts can never be
verified. The `movie2` migration found 92 conflicts in six titles already on
raid-pc from another disk: 5 were video files and 87 were Media Center Master
artwork (`.jpg`) and metadata (`.xml`). Those files are regenerated whenever a
library is refreshed, so the two copies differ routinely and neither is
irreplaceable; reviewing each one by hand adds nothing. Video files are the
data that must not be silently replaced.

## Decisions

1. **Metadata files are compared by age, not reported as conflicts.** A
   regular file whose extension is listed in `metadataExtensions` (default
   `jpg`, `jpeg`, `png`, `xml`, `nfo`; case-insensitive) and that differs from
   the destination copy is:
   - **replaced** when the source copy is strictly newer: it is copied in a
     separate rsync pass without `--ignore-existing`, keeping the source's
     modification time, so it then counts as identical;
   - **kept** when the destination copy is as new or newer: the destination is
     left alone and the source copy is treated as superseded.
   Every other differing file, including all video files, stays a conflict and
   is never overwritten. An empty `metadataExtensions` restores ADR 001
   behaviour.
2. **Kept files satisfy verification and checks.** A kept metadata file is not
   checksummed and does not fail verification. `--check` accepts a destination
   metadata file that is newer than the verified one (a media manager updated
   it), and fails if it is older or if any other file changed.
3. **Removal deletes superseded source metadata.** A kept file's source copy is
   in the verified manifest and is deleted by `--remove-source` like any other
   verified file; the newer copy on the destination remains.

## Consequences

- A migration with only metadata differences completes and can be verified
  without manual work; video conflicts still stop it.
- The destination can only move forward in time for these files, so another
  mapping that verified an older copy still passes `--check`.
- Which copy wins depends on modification times. A source file with a wrong,
  future timestamp would replace a correct destination copy; metadata is
  regenerable, so this is accepted.
- The removed source copy of a kept file has no other copy; its newer
  replacement is assumed to be at least as good.
