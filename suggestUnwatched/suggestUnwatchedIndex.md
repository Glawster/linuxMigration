# suggestUnwatched

Suggest video folders that Plex has not watched, so they can be considered for
removal. The scan starts at the current directory.

## Documentation

- [How folders are ranked](documentation/ranking.md)

## Install

    cd ~/bin/suggestUnwatched
    conda env create -f environment.yml
    conda activate suggestUnwatched
    python -m pip install -e .

`organiseMyProjects` is installed from the GitHub `0.6` tag. If a failed
environment is still present, remove it before creating it again:

    conda env remove -n suggestUnwatched

Run it from the library directory you want to inspect:

    cd /mnt/video3/TV
    suggestUnwatched

The chooser lists the oldest unwatched folders. `x` marks the highlighted
show as exempt and the next oldest folder takes its place. `u` restores the
highlighted exempt show. `q` quits. Exempt show names are saved in
`~/.config/suggestUnwatched/config.json`.

On exit, the shows still suggested are listed again and written as `rm`
commands to `removeShows.sh` in the working directory you started the scan
from. Review that file before you run it. The chooser does not run it.

Print the list without the chooser:

    suggestUnwatched --report
    suggestUnwatched /mnt/video3/TV --count 5 --report

The command does not move or delete folders. It logs the repository version
(see "Versioning and releases" in
[additional instructions](../.github/additional-instructions.md)) when it
starts.

## Tests

    conda run -n suggestUnwatched python -m pytest ~/bin/suggestUnwatched

Requirement: [004 Suggest unwatched video folders](../project/requirements/features/004-suggestUnwatched.md).
