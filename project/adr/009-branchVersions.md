# 009: A version number for every branch of work

- Status: Accepted
- Date: 2026-10-26
- Amends: [ADR 008](008-repositoryVersion.md)

## Context

ADR 008 gave the repository one version that changes only at a release, so
every change merged between releases ran as `v1.3-N-g<commit>`. That number
says how far the code is from the release, not which piece of work it is, and
nothing tied a branch's work to a version. The managed OMP release guide
already numbers development work as alpha versions of the next release
(`1.4a1`, `1.4a2`), but it assumes release branches, which this repository
does not use.

## Decisions

1. **Each branch of work takes the next unused alpha number** of the coming
   release (`1.4a1`, `1.4a2`, ... after `1.3`) in `VERSION`, as its first
   commit. A number is unused when no `v*` tag, no `main` and no local or
   remote branch holds it; `branchVersion start` picks it.
2. **No release branches.** Branches are squash-merged straight into `main`,
   so `main` carries the number of the last merged branch. This is the one
   exception to the managed release guide; the rest of its alpha-version rules
   apply.
3. **Every merge is tagged.** The squash-merge commit on `main` gets the
   annotated tag `v<VERSION>` (`branchVersion tag`), with the merge commit's
   subject as its message, so a version finds its pull request and its code.
4. **Tools show the branch's number.** Away from a tag, when `VERSION` differs
   from the tag `git describe` counts from, `repoVersion.sh` and
   `repoVersion.py` show both, for example `1.4a3 (v1.4a2-1-g1a2b3c4)`.
5. **Releases are unchanged in form**: `VERSION` drops the alpha suffix
   (`1.4`), the merge is tagged `v1.4`, and the next branch is `1.5a1`.
6. **Numbering started at 1.4a1** with hardwareSnapshot (#110), tagged after
   its merge.

## Consequences

- Every version names one piece of work, and `git tag -n1` lists them with
  their pull requests.
- Two open branches always change the `VERSION` line, so the second to merge
  has a conflict there; it keeps its own number.
- Version numbers follow the order branches were started, not merged, so tags
  on `main` can appear out of numeric order.
- The `v1.4a1` tag is on a commit whose `VERSION` still reads `1.3`, because
  the scheme was adopted after that merge.
