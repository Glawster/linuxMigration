# NFS exports and mounts

## Roles and packages

NFS uses two distinct roles:

- an exporting machine needs `nfs-kernel-server`;
- a machine mounting remote shares needs `nfs-common`.

Declare the appropriate package in that machine's YAML profile. A machine may
have both roles. NFSv4 is used for managed mounts.

## Exporting a local filesystem

First give the local disk a stable mount point using its filesystem UUID. Do not
export an intermittently mounted path or the raw block device. Then declare the
export and restrict it to the consuming machine's fixed address:

```yaml
packages:
  apt:
    - nfs-kernel-server

nfsExports:
  - /mnt/games 192.0.2.10(rw,sync,no_subtree_check)
```

The address is an example from a documentation-only range. Replace it with the
real reserved address of the client. Avoid `*`, broad subnets, `no_root_squash`,
and world-writable filesystem permissions. The bootstrap writes only
`/etc/exports.d/linux-bootstrap.exports` and reloads exports with `exportfs -ra`.

NTFS can be exported, but Linux ownership and mode behavior is determined by its
local mount options. For shared game data, verify UID/GID mapping and write
behavior locally before allowing a remote client to write.

## Mounting a remote export

Declare the client package and each remote source, local target, and optional
mount options:

```yaml
packages:
  apt:
    - nfs-common

nfsMounts:
  - andy-pc:/srv/media /mnt/andy-media ro,_netdev,nofail,x-systemd.automount
```

When options are omitted, the bootstrap uses
`defaults,_netdev,nofail,x-systemd.automount`. It manages only the marked NFS
block in `/etc/fstab`, creates missing mount-point directories, and mounts
inactive shares. Existing unrelated fstab content is preserved.

Use `ro` initially. Change to `rw` only after confirming server permissions and
matching numeric user/group IDs where shared ownership matters.

## Firewall and verification

NFSv4 primarily uses TCP port 2049. Permit it only from the trusted LAN or the
specific client address. Verify configuration without mutation:

```bash
./bootstrap.sh --profile tv-pc --status
```

Useful manual checks are:

```bash
exportfs -v
showmount -e tv-pc
findmnt -t nfs,nfs4
```

Do not re-export a directory that is itself an NFS mount. Export the original
directory directly from the machine that owns its filesystem.
