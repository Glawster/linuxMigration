# World of Warcraft through Battle.net

The optional `wow` profile installs Blizzard's Windows Battle.net launcher
through UMU and GE-Proton. It does not use Steam and it does not store Blizzard
credentials in the profile.

Preview or apply the profile:

```bash
./bootstrap.sh install --profile wow
./bootstrap.sh install --profile wow --confirm
```

Its configuration is:

```yaml
wow:
  enabled: true
  installDir: /mnt/games/wow
```

Bootstrap creates a dedicated prefix at
`${XDG_DATA_HOME:-~/.local/share}/wow/prefix` and maps Wine drive `G:` to
`/mnt/games`. Battle.net setup is interactive. Sign in with the existing
Blizzard account, install World of Warcraft, and choose `G:\wow` as the game
location. Authentication, game selection, updates, and optional components
remain managed by Battle.net.

After Battle.net is installed, use `battlenet`. Run bootstrap again after WoW
finishes installing to create the direct `wow` helper when `_retail_/Wow.exe`
is detected. Check configuration without changes with:

```bash
./bootstrap.sh status --profile wow
```

The legacy repository-root `setupBattlenetPrefix.sh` is not used: it deletes
prefixes and pins an obsolete Wine-GE release. The bootstrap module is
idempotent and shares the maintained UMU/GE-Proton installation used for other
standalone Windows games while keeping WoW in its own prefix.
