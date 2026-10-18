<!-- deployed from Glawster/organiseMyProjects release 0.9 -- do not edit directly -->
# Release Process

## Purpose

This guide defines a safe, repeatable release workflow for this repository.

## Versioning Policy

- Released versions are immutable once published.
- Existing tags `0.3` and `0.4` are retained as historical release tags.
- Standard release tags use `vX.Y`.
- Patch tags `vX.Y.Z` are allowed when needed for exceptional hotfix releases.
- Pre-release builds use tags such as `v0.5-rc1`.

## Branch Model

- `main` represents the latest released production state.
- Active development continues on release branches such as `release/0.5`.
- Changes land on `main` only when they are release-ready.

## Repository Protection Rules

- Protect `main` from force pushes and deletion.
- Require pull requests to merge into `main`.
- Protect release tags with a Tag Ruleset so existing tags cannot be moved or
   deleted.
- Use a ruleset target pattern that matches release tags, for example `v*`.

## Release Checklist

1. Confirm the target release branch is green in CI.
2. Run local validation:
   - `pytest`
   - `runLinter .`
   - `runLinter --markup`
   - If markup issues are reported, run `runLinter --markup --fix` and then
     rerun `runLinter --markup`.
3. Confirm `organiseMyProjects/version.py`, package metadata, release notes and
   documentation all identify the intended release.
4. Merge the release branch into `main` through a pull request.
5. Pull latest `main` locally with `git pull --ff-only`.
6. Create an annotated release tag:
   - `git tag -a v0.5 -m "Release v0.5"`
7. Push the tag:
   - `git push origin v0.5`
8. Verify the GitHub release artifacts and notes.

## Hotfix Workflow

1. Branch from `main`, for example `hotfix/0.3.1`.
2. Apply the fix and validate tests.
3. Merge into `main` with a pull request.
4. If a patch release is required, tag with an annotated patch tag such as
   `v0.3.1`.
5. Cherry-pick or merge the fix into active release branches as needed.

## Temporary Tag-Rule Rollback Checklist

Use this checklist only when a protected release tag must be corrected.

1. Identify and record the intended target commit hash.
2. In GitHub Rulesets, temporarily allow tag update or deletion for the exact
   tag (or use an admin bypass if your ruleset allows it).
3. Delete the existing remote tag:
   - `git push origin :refs/tags/v0.5`
4. Delete the local tag copy:
   - `git tag -d v0.5`
5. Recreate the tag at the intended commit:
   - `git tag -a v0.5 <commit> -m "Release v0.5"`
6. Push the corrected tag:
   - `git push origin v0.5`
7. Verify the tag points to the expected commit locally and remotely.
8. Re-enable strict tag protection immediately.

Rulesets note:

- GitHub legacy Protected Tags are deprecated; manage release-tag protections in
   Repository Rulesets.

Verification commands:

- `git rev-parse v0.5^{}`
- `git ls-remote --tags origin v0.5 v0.5^{}`

## Tag Conflict Prevention

- Never reuse an existing release tag name.
- Never retag a published version.
- Use annotated tags for all releases.
- If a mistaken local tag exists, back it up before replacing it.
