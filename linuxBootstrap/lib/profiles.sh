#!/usr/bin/env bash

declare -ag loadedProfiles=() profileAptPackages=() profileFlatpakPackages=()
declare -ag profileSnapPackages=() profileServices=() profileRepositories=()
declare -Ag profileGit=() loadingProfiles=()
profileHostname=""
profileStaticIp=""

profileResolve() {
    local name="$1" role="$projectDir/profiles/$name.yaml" host="$projectDir/profiles/hosts/$name.yaml"
    if [[ -f "$role" ]]; then printf '%s\n' "$role"; return; fi
    if [[ -f "$host" ]]; then printf '%s\n' "$host"; return; fi
    logError "profile not found: $name"
    return 1
}

profileListRead() {
    local file="$1" key="$2"
    awk -v wanted="$key" '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        /^[^[:space:]][^:]*:/ { section=$1; sub(/:$/, "", section); next }
        section == wanted && /^[[:space:]]+-[[:space:]]+/ {
            sub(/^[[:space:]]+-[[:space:]]+/, ""); sub(/[[:space:]]+#.*$/, ""); print
        }
    ' "$file"
}

profileScalarRead() {
    local file="$1" key="$2"
    awk -F: -v wanted="$key" '$1 == wanted {sub(/^[[:space:]]+/, "", $2); print $2; exit}' "$file"
}

profileMapRead() {
    local file="$1" key="$2"
    awk -v wanted="$key" '
        /^[^[:space:]][^:]*:/ { section=$1; sub(/:$/, "", section); next }
        section == wanted && /^[[:space:]]+[A-Za-z0-9_-]+:/ {
            line=$0; sub(/^[[:space:]]+/, "", line); split(line, parts, ":");
            value=substr(line, index(line, ":") + 1); sub(/^[[:space:]]+/, "", value);
            print parts[1] "=" value
        }
    ' "$file"
}

profileLoad() {
    local name="$1" file inherited item key value
    for item in "${loadedProfiles[@]}"; do [[ "$item" == "$name" ]] && return; done
    if [[ "${loadingProfiles[$name]:-0}" == 1 ]]; then
        logError "profile inheritance cycle detected at: $name"
        return 2
    fi
    loadingProfiles["$name"]=1
    file="$(profileResolve "$name")"
    while IFS= read -r inherited; do [[ -n "$inherited" ]] && profileLoad "$inherited"; done < <(profileListRead "$file" profiles)
    unset 'loadingProfiles[$name]'
    loadedProfiles+=("$name")
    logVerbose "loaded profile: $name"
    mapfile -t items < <(profileListRead "$file" apt); profileAptPackages+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" flatpak); profileFlatpakPackages+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" snap); profileSnapPackages+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" services); profileServices+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" repositories); profileRepositories+=("${items[@]}")
    value="$(profileScalarRead "$file" hostname)"; [[ -z "$value" ]] || profileHostname="$value"
    value="$(profileScalarRead "$file" staticIp)"; [[ -z "$value" ]] || profileStaticIp="$value"
    while IFS='=' read -r key value; do [[ -n "$key" ]] && profileGit["$key"]="$value"; done < <(profileMapRead "$file" git)
}

profilesLoad() {
    local profile
    for profile in "$@"; do profileLoad "$profile"; done
}
