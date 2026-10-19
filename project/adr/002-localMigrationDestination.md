# 002: Local destinations alongside raid-pc

- Status: Accepted
- Date: 2026-10-19
- Requirement: [001 raid-pc storage migration](../requirements/features/001-raidMigration.md)
- Related: [ADR 001](001-raidMigrationSafety.md)

## Context

Personal pictures and home video stay on andy-pc, on a new internal disk
mounted at `/mnt/media`, while bulk Movies and TV move to raid-pc. Some source
disks are split between the two (`/mnt/myPictures/Movies` goes to raid-pc, the
rest of `/mnt/myPictures` stays local). `migrateToRaid` was built around one
remote destination: global `destinationMount`, every operation over SSH, and a
SAFE verdict gated on raid-pc parity. `/mnt/media` is a single disk with no
parity.

## Decisions

1. **One tool, one safety model.** Local copies use the same `migrateToRaid`
   workflow, state, manifests, verification and removal as raid-pc copies.
   Only the transport differs: destination scripts run under local `bash`
   instead of SSH, and rsync is given a local path. A second tool would
   duplicate the safety logic.
2. **Per-mapping target.** A mapping sets `"target": "local"` to use the single
   top-level `localDestination`; the default remains raid-pc, so existing
   configurations are unchanged.
3. **Positive identity of the local destination.** `localDestination.uuid` is
   required. Before copying and on every `--check`, the filesystem mounted at
   `localDestination.mount` must exist, carry that UUID (and `fsType`, if set),
   contain the destination, and differ from the source filesystem. An empty
   mount-point directory on the root filesystem is never a destination.
4. **Protection per destination.** SAFE TO REMOVE requires the protection of
   each mapping's own destination: SnapRAID parity for raid-pc, and for the
   local destination either a configured check or an explicit
   `"required": false`. `/mnt/media` is configured with `"required": false`:
   it is the new authoritative internal copy of Pictures and personal Video,
   no parity or backup layer has been designed for it, and a placeholder that
   can never pass would stop the USB source disks from ever being retired
   after a full verification. This accepts single-copy storage; it does not
   claim `/mnt/media` is backed up or redundant. Without either setting a
   local mapping is never SAFE. raid-pc protection cannot be disabled.
   Every SAFE verdict states its basis (`SNAPRAID PARITY VERIFIED` versus
   `DESTINATION ACCEPTED AS AUTHORITATIVE (single copy, not redundant)`), so
   single-copy SAFE is never mistaken for redundancy.
5. **No provisioning.** The tool never creates, formats or mounts `/mnt/media`.

## Consequences

- Local mappings can be migrated before the raid-pc layout is decided.
- A disk split between raid-pc and `/mnt/media` is SAFE only when its raid-pc
  part has parity and its local part meets the local protection setting.
- Once fully verified, local-only content has exactly one copy, on
  `/mnt/media`. A failure of that disk loses it until a backup is designed.
- Content that no mapping covers, such as `/mnt/myVideo/encrypted`, keeps its
  disk NOT SAFE TO REMOVE DISK until it is dealt with.
- The name `migrateToRaid` no longer describes every destination; it is kept
  for continuity.
