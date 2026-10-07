# Media library workflow

The `media-library` profile provides a Linux workflow comparable to a Media Center Master setup:

- tinyMediaManager for manual metadata and artwork;
- FileBot for automated renaming and sorting;
- qBittorrent for torrent downloads;
- Sonarr for TV automation;
- Radarr for movie automation;
- Jellyfin as the media library/server;
- Private Internet Access (PIA) as the VPN.

## Storage layout

On `andy-pc`, `/mnt/video2` is exported over NFS to `tv-pc`.

On `tv-pc`, bootstrap mounts it at the same path:

```text
/mnt/video2
```

qBittorrent is preconfigured with:

```text
Incomplete downloads: /mnt/video2/Downloads
Completed downloads:  /mnt/video2/toFile
```

Keeping both paths on the same underlying filesystem avoids an unnecessary cross-filesystem copy between incomplete and completed downloads. Sonarr/Radarr library roots should remain separate from the download directory even when they live on the same filesystem.

## Install on tv-pc

Preview first:

```bash
./bootstrap.sh install --profile tv-pc
```

Then apply:

```bash
./bootstrap.sh install --profile tv-pc --confirm
```

The Sonarr upstream installer is interactive. When prompted for its service user and group, use:

```text
user:  andy
group: andy
```

This keeps filesystem access consistent with qBittorrent and the NFS-mounted media storage.

## SSH between andy-pc and tv-pc

Bootstrap installs and enables OpenSSH server and adds aliases for both hosts. Private keys are deliberately not stored in the repository.

If `~/.ssh/id_ed25519` does not already exist on a machine, create it once:

```bash
ssh-keygen -t ed25519
```

Then enrol each public key once from each machine:

```bash
ssh-copy-id tv-pc
ssh-copy-id andy-pc
```

After that, normal SSH should be passwordless in both directions:

```bash
ssh tv-pc
ssh andy-pc
```

## Private Internet Access and qBittorrent

PIA is installed from the vendor Linux installer and its download is checksum verified. Login remains a user action because credentials must not be stored in bootstrap profiles.

After logging into PIA, enable its kill switch. In qBittorrent, also bind torrent traffic to the PIA network interface under Advanced settings. The exact interface name depends on the PIA protocol and current client configuration, so bootstrap does not hard-code an interface name.

## Jellyfin

Jellyfin is installed as the default media server for this profile. Initial library creation remains a GUI setup task because the final Movies/TV library roots have not yet been defined in the bootstrap profile.

## Sonarr and Radarr

Configure qBittorrent as the download client and use distinct categories, for example:

```text
Sonarr: tv
Radarr: movies
```

The download client completed path is `/mnt/video2/toFile`. Configure separate TV and movie library roots elsewhere under the NFS-backed storage once their final directory layout is decided.
