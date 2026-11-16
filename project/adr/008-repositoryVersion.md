# 008: One version and release tag for the whole repository

- Status: Accepted; amended by [ADR 009](009-branchVersions.md) (every branch
  of work gets its own alpha version, and every merge is tagged)
- Date: 2026-10-24
- Related: [ADR 006](006-migrateOnHostWithDisk.md)

## Context

This repository is deployed as a whole: each machine runs its tools from its
own `~/bin` checkout, and andy-pc and raid-pc can be on different commits or
branches. To fetch a known version and to see, in every run, which code is
running, the repository needs a version and tags. `migrateToRaid` briefly had
its own version number, but a tag names a commit of the whole repository, so
per-tool numbers and repository tags would disagree.

## Decisions

1. **One repository version.** `VERSION` at the repository root holds the
   release number (`X.Y`, or `X.Y.Z` for a hotfix). Tools do not keep their own
   version numbers; what changed for each tool is recorded in
   `documentation/releaseNotes.md`.
2. **Annotated `vX.Y` tags on `main`.** Each release is an annotated tag on the
   squash-merged `main` commit that set `VERSION`. Tags are never moved or
   reused. There are no release branches.
3. **Tools report `git describe`.** Tools print the checkout's description
   against its release tags, from `repoVersion.sh` (Bash) or `repoVersion.py`
   (Python): `v1.3` on a release, `v1.3-4-g1a2b3c4` after it, with `-dirty` for
   uncommitted changes; the `VERSION` file is the fallback without git.
4. **The process is recorded** in `.github/additional-instructions.md`
   ("Versioning and releases"), as this repository's exception to the managed
   release guide's release-branch model.

## Consequences

- A run's header shows exactly what ran, including unreleased or modified
  code, on each machine.
- Every tool shares the version, so a release that changes one tool also
  changes the number for the others.
- Other tools adopt the helpers when they are next changed; `migrateToRaid` is
  the first.
