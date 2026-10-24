# How folders are suggested

`suggestUnwatched` scans the current directory, or the directory you pass as
`root`. It finds directories that directly contain video files, then rolls
those seasons and extras up to one row per show. The idea is that we identify
shows or movies that are unlikely to be watched and remove them from disk to
conserve space.

A show is unwatched when none of its video files have a Plex view count, a
last-viewed time, or a resume offset. One watched episode keeps the whole
show off the list. Watched state comes from the local Plex library database.
Media Center Master and WD TV watched markers are not used. Files that are
not in Plex count as unwatched.

Suggestions are ordered by:

1. the oldest Plex last-viewed time, when a folder has one
2. otherwise the oldest `<FirstAired>` date in that folder's Media Center
   Master episode XML, or `series.xml` on the folder or a parent up to the
   scan root
3. otherwise the oldest Plex `originally_available_at` date for files in the
   folder

Unwatched shows have no Plex watch time, so the suggested shows are the ones
with the oldest episode air dates. Size and video count cover the whole show.
The default report lists five. The command does not move or delete folders.

In a terminal, the chooser opens instead of printing. It lists the oldest
suggestions. `x` exempts the highlighted show, saves that name, and fills the
row with the next oldest folder that is still eligible. `u` restores the
highlighted exempt show so its folders can be suggested again. `q` closes the
chooser. On exit the terminal lists the shows still suggested for archive or
deletion and writes `rm` commands for those show folders to `removeShows.sh`
in the working directory the scan was started from. The command does not run
that script. `--report` prints the list and skips the chooser.

The exempt names are show folder names. The show name comes from the
directory that holds `series.xml`, or from the first directory under the scan
root when that file is absent. Names are kept
in `~/.config/suggestUnwatched/config.json` under `exemptShows`. A folder is
skipped when any directory in its path matches an exempt name.

The Plex library database is readable by this login, so the command does not
ask for a password and does not use the login-session password cache.
