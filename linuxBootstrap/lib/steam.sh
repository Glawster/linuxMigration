#!/usr/bin/env bash

steamAppsApply() {
    local entry appId name
    for entry in "$@"; do
        read -r appId name <<< "$entry"
        [[ "$appId" =~ ^[0-9]+$ && -n "$name" ]] || { logError "invalid Steam app entry: $entry"; return 2; }
        if _steamAppInstalled "$appId"; then
            itemSkip "Steam app already installed: $name ($appId)"
        else
            (( ${statusMode:-0} )) || logWarning "Steam may require account interaction to install $name"
            changeRun "request Steam app install: $name ($appId)" steam "steam://install/$appId"
        fi
    done
}

_steamAppInstalled() {
    local appId="$1" root
    for root in "$HOME/.local/share/Steam" "$HOME/.steam/steam"; do
        [[ -f "$root/steamapps/appmanifest_$appId.acf" ]] && return 0
    done
    return 1
}
