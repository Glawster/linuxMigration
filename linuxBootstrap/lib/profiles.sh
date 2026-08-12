#!/usr/bin/env bash

declare -ag loadedProfiles=() profileAptPackages=() profileFlatpakPackages=()
declare -ag profileSnapPackages=() profileServices=() profileRepositories=()
declare -ag profileHostEntries=() profileNfsExports=() profileNfsMounts=()
declare -ag profileInstallers=() profileSteamApps=()
declare -ag profileManagedFiles=() profileVscodeExtensions=()
declare -Ag profileDcs=() profileGit=() profileNetwork=() loadingProfiles=()
profileHostname=""
profileStaticIp=""
profileExpectedIp=""
profileMasterName=""
profileMasterHostname=""

profileMasterResolve() {
    local file masterValue hostnameValue name masterCount=0
    for file in "$projectDir"/profiles/hosts/*.yaml; do
        [[ -f "$file" ]] || continue
        masterValue="$(profileScalarRead "$file" master)"
        case "${masterValue,,}" in
            ""|false) continue ;;
            true) ;;
            *)
                logError "invalid master value in $file: $masterValue (expected true or false)"
                return 2
                ;;
        esac
        ((masterCount += 1))
        name="$(basename "$file" .yaml)"
        hostnameValue="$(profileScalarRead "$file" hostname)"
        [[ -n "$hostnameValue" ]] || {
            logError "master host profile must define hostname: $name"
            return 2
        }
        profileMasterName="$name"
        profileMasterHostname="$hostnameValue"
    done
    if ((masterCount != 1)); then
        logError "exactly one host profile must set master: true (found $masterCount)"
        return 2
    fi
}

profileResolve() {
    local name="$1" role host
    role="$projectDir/profiles/$name.yaml"
    host="$projectDir/profiles/hosts/$name.yaml"
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

profileNestedListRead() {
    local file="$1" parent="$2" key="$3"
    awk -v wantedParent="$parent" -v wantedKey="$key" '
        /^[[:space:]]*#/ || /^[[:space:]]*$/ { next }
        /^[^[:space:]][^:]*:/ {
            parent=$1; sub(/:$/, "", parent); key=""; next
        }
        parent == wantedParent && /^[[:space:]][[:space:]][^[:space:]][^:]*:/ {
            line=$0; sub(/^[[:space:]]+/, "", line)
            key=line; sub(/:.*$/, "", key); next
        }
        parent == wantedParent && key == wantedKey && /^    -[[:space:]]+/ {
            line=$0; sub(/^[[:space:]]+-[[:space:]]+/, "", line)
            sub(/[[:space:]]+#.*$/, "", line); print line
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
    mapfile -t items < <(profileNestedListRead "$file" packages apt); profileAptPackages+=("${items[@]}")
    mapfile -t items < <(profileNestedListRead "$file" packages flatpak); profileFlatpakPackages+=("${items[@]}")
    mapfile -t items < <(profileNestedListRead "$file" packages snap); profileSnapPackages+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" services); profileServices+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" repositories); profileRepositories+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" hosts); profileHostEntries+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" nfsExports); profileNfsExports+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" nfsMounts); profileNfsMounts+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" installers); profileInstallers+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" steamApps); profileSteamApps+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" managedFiles); profileManagedFiles+=("${items[@]}")
    mapfile -t items < <(profileListRead "$file" vscodeExtensions); profileVscodeExtensions+=("${items[@]}")
    value="$(profileScalarRead "$file" hostname)"; [[ -z "$value" ]] || profileHostname="$value"
    value="$(profileScalarRead "$file" staticIp)"; [[ -z "$value" ]] || profileStaticIp="$value"
    value="$(profileScalarRead "$file" expectedIp)"; [[ -z "$value" ]] || profileExpectedIp="$value"
    while IFS='=' read -r key value; do [[ -n "$key" ]] && profileGit["$key"]="$value"; done < <(profileMapRead "$file" git)
    while IFS='=' read -r key value; do [[ -n "$key" ]] && profileNetwork["$key"]="$value"; done < <(profileMapRead "$file" network)
    while IFS='=' read -r key value; do [[ -n "$key" ]] && profileDcs["$key"]="$value"; done < <(profileMapRead "$file" dcs)
}

profilesLoad() {
    local profile
    profileMasterResolve
    for profile in "$@"; do profileLoad "$profile"; done
}

profileAdd() {
    local name="$1" target
    target="$projectDir/profiles/$name.yaml"
    [[ "$name" =~ ^[a-z][a-z0-9-]*$ ]] || { logError "invalid profile name: $name"; return 2; }
    [[ ! -e "$target" ]] || { logError "profile already exists: $name"; return 2; }
    changeRun "create role profile: $name" profileCreate "$name" "$target"
}

profileCreate() {
    local name="$1" target="$2"
    printf 'name: %s\n\napt:\n\nflatpak:\n\nservices:\n' "$name" > "$target"
}

profileShow() {
    local name="$1" item key
    profilesLoad "$name"
    printf 'Profile: %s\n' "$name"
    printf 'Inheritance: %s\n' "${loadedProfiles[*]}"
    [[ -z "$profileHostname" ]] || printf 'Hostname: %s\n' "$profileHostname"
    [[ -z "$profileExpectedIp" ]] || printf 'Expected IP: %s\n' "$profileExpectedIp"
    printf 'Master: %s\n' "$([[ "$name" == "$profileMasterName" ]] && echo true || echo false)"
    for item in "${profileAptPackages[@]}"; do printf 'apt: %s\n' "$item"; done
    for item in "${profileFlatpakPackages[@]}"; do printf 'flatpak: %s\n' "$item"; done
    for item in "${profileSnapPackages[@]}"; do printf 'snap: %s\n' "$item"; done
    for item in "${profileServices[@]}"; do printf 'service: %s\n' "$item"; done
    for item in "${profileHostEntries[@]}"; do printf 'host: %s\n' "$item"; done
    for item in "${profileNfsExports[@]}"; do printf 'nfsExport: %s\n' "$item"; done
    for item in "${profileNfsMounts[@]}"; do printf 'nfsMount: %s\n' "$item"; done
    for item in "${profileInstallers[@]}"; do printf 'installer: %s\n' "$item"; done
    for item in "${profileSteamApps[@]}"; do printf 'steamApp: %s\n' "$item"; done
    for item in "${profileManagedFiles[@]}"; do printf 'managedFile: %s\n' "$item"; done
    for item in "${profileVscodeExtensions[@]}"; do printf 'vscodeExtension: %s\n' "$item"; done
    for key in "${!profileGit[@]}"; do printf 'git.%s: %s\n' "$key" "${profileGit[$key]}"; done
    for key in "${!profileNetwork[@]}"; do printf 'network.%s: %s\n' "$key" "${profileNetwork[$key]}"; done
    for key in "${!profileDcs[@]}"; do printf 'dcs.%s: %s\n' "$key" "${profileDcs[$key]}"; done
}

profilesList() {
    local file name
    profileMasterResolve
    printf 'Role profiles\n'
    for file in "$projectDir"/profiles/*.yaml; do
        [[ -f "$file" ]] || continue
        name="$(basename "$file" .yaml)"
        printf '  %s\n' "$name"
    done
    printf 'Host profiles\n'
    for file in "$projectDir"/profiles/hosts/*.yaml; do
        [[ -f "$file" ]] || continue
        name="$(basename "$file" .yaml)"
        if [[ "$name" == "$profileMasterName" ]]; then
            printf '  %s (master: %s)\n' "$name" "$profileMasterHostname"
        else
            printf '  %s\n' "$name"
        fi
    done
}

profileKeysValidate() {
    local file="$1" key
    while IFS= read -r key; do
        case "$key" in
            name|hostname|master|expectedIp|staticIp|profiles|packages|apt|flatpak|snap|services|repositories|git|network|dcs|hosts|nfsExports|nfsMounts|installers|steamApps|managedFiles|vscodeExtensions) ;;
            *) logError "unsupported profile key in $file: $key"; return 2 ;;
        esac
    done < <(awk -F: '/^[A-Za-z][A-Za-z0-9_-]*:/ {print $1}' "$file")
}

profilesValidate() {
    local file name
    profileMasterResolve
    for file in "$projectDir"/profiles/*.yaml "$projectDir"/profiles/hosts/*.yaml; do
        [[ -f "$file" ]] || continue
        profileKeysValidate "$file"
        name="$(basename "$file" .yaml)"
        profileLoad "$name"
    done
    logSuccess "all profiles are valid"
}
