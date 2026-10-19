#!/usr/bin/env bash
# Configuration, persisted state and manifest handling for migrateToRaid.
# Sourced by lib/raidMigration.sh; not a bootstrap module.
#
# Manifest records are NUL-terminated and tab-separated:
#   <type>\t<size>\t<mtime>\t<relative path>
# The path is always the last field, so it may contain tabs, newlines or any
# other byte except NUL. Directories are recorded with size and mtime 0.

checksumCommands=(sha256sum b2sum md5sum)
configFile=""
destinationFsType=""
destinationMount=""
excludeNames=()
localFsType=""
localMount=""
localProtectionCommand=""
localProtectionName=""
localProtectionRequired=true
localProtectionSuccessCodes=(0)
localSource=""
localUuid=""
protectionCommand=""
protectionName=""
protectionSuccessCodes=(0)
mappingNames=()
minFreeBytesAfter=10737418240
remoteHost=""
remoteUser=""
stateDir=""
checksumCommand="sha256sum"

declare -gA mapDest=()
declare -gA mapEnabled=()
declare -gA mapExcludes=()
declare -gA mapLabel=()
declare -gA mapMount=()
declare -gA mapSource=()
declare -gA mapTarget=()
declare -gA mapType=()
declare -gA mapUuid=()
declare -gA state=()

## config

configLoad() {
    local file="$1" name label type source dest enabled uuid mount excludes target
    if [[ ! -f "$file" ]]; then
        log_error "configuration not found: $file"
        log_info "copy configs/migrateToRaid/config.json to that path and review it"
        return 1
    fi
    if ! jq -e 'type == "object" and (.mappings | type == "array")' "$file" >/dev/null 2>&1; then
        log_error "invalid configuration (expected a JSON object with a mappings array): $file"
        return 1
    fi
    remoteHost="$(jq -r '.remoteHost // "raid-pc"' "$file")"
    remoteUser="$(jq -r '.remoteUser // ""' "$file")"
    destinationMount="$(jq -r '.destinationMount // ""' "$file")"
    minFreeBytesAfter="$(jq -r '.minFreeBytesAfter // 10737418240' "$file")"
    checksumCommand="$(jq -r '.checksum // "sha256sum"' "$file")"
    destinationFsType="$(jq -r '.destinationFsType // ""' "$file")"
    protectionName="$(jq -r '.protection.name // "raid-pc parity protection"' "$file")"
    protectionCommand="$(jq -r '.protection.command // ""' "$file")"
    mapfile -t protectionSuccessCodes < <(jq -r '(.protection.successExitCodes // [0])[] | tostring' "$file")
    mapfile -t excludeNames < <(jq -r '(.excludes // ["lost+found", "$RECYCLE.BIN", "System Volume Information"])[]' "$file")
    # The optional local destination is a disk on the machine running the tool
    # (/mnt/media on andy-pc, or the /mnt/storage pool on raid-pc). Its
    # protection is required unless explicitly set to false.
    localMount="$(jq -r '.localDestination.mount // "" | sub("/+$"; "")' "$file")"
    localFsType="$(jq -r '.localDestination.fsType // ""' "$file")"
    localSource="$(jq -r '.localDestination.source // ""' "$file")"
    localUuid="$(jq -r '.localDestination.uuid // ""' "$file")"
    localProtectionName="$(jq -r '.localDestination.protection.name // "local destination protection"' "$file")"
    localProtectionCommand="$(jq -r '.localDestination.protection.command // ""' "$file")"
    localProtectionRequired="$(jq -r 'if .localDestination.protection.required == false then "false" else "true" end' "$file")"
    mapfile -t localProtectionSuccessCodes < <(jq -r '(.localDestination.protection.successExitCodes // [0])[] | tostring' "$file")

    mappingNames=()
    mapDest=() mapEnabled=() mapExcludes=() mapLabel=() mapMount=() mapSource=() mapTarget=() mapType=() mapUuid=()
    while IFS=$'\x1f' read -r name label type source dest enabled uuid mount excludes target; do
        if [[ ! "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
            log_error "invalid mapping name in configuration: '$name'"
            return 1
        fi
        if [[ -n "${mapSource[$name]+x}" ]]; then
            log_error "duplicate mapping name in configuration: $name"
            return 1
        fi
        if [[ "$source" != /* || "$source" == "/" ]]; then
            log_error "mapping $name: source must be an absolute path below /: '$source'"
            return 1
        fi
        mount="${mount%/}"
        if [[ "$mount" != /* || ( "${source%/}" != "$mount" && "${source%/}" != "$mount"/* ) ]]; then
            log_error "mapping $name: source must be the mountPoint or a folder inside it: '$source' / '$mount'"
            return 1
        fi
        if [[ "$enabled" != true && "$enabled" != false ]]; then
            log_error "mapping $name: enabled must be true or false"
            return 1
        fi
        if [[ "$target" != remote && "$target" != local ]]; then
            log_error "mapping $name: target must be remote (raid-pc) or local: '$target'"
            return 1
        fi
        mappingNames+=("$name")
        mapLabel[$name]="$label"
        mapType[$name]="${type,,}"
        mapSource[$name]="${source%/}"
        mapDest[$name]="${dest%/}"
        mapEnabled[$name]="$enabled"
        mapUuid[$name]="$uuid"
        mapMount[$name]="$mount"
        mapExcludes[$name]="$excludes"
        mapTarget[$name]="$target"
    done < <(jq -r '.mappings[] | [
            (.name // ""), (.label // .name // ""), (.type // "files"),
            (.source // ""), (.destination // ""),
            ((.enabled // false) | tostring), (.uuid // ""),
            (.mountPoint // .source // ""), ((.excludes // []) | join("/")),
            (.target // "remote")
        ] | map(tostring | gsub("[\u001f\n]"; " ")) | join("\u001f")' "$file")
    configFile="$file"
    _configOverlapCheck
}

# Lists the names excluded from a mapping: the global excludes plus the
# mapping's own top-level excludes (stored "/"-separated).
configMappingExcludes() {
    local name="$1" item
    for item in "${excludeNames[@]}"; do
        printf '%s\n' "$item"
    done
    [[ -n "${mapExcludes[$name]}" ]] && tr '/' '\n' <<<"${mapExcludes[$name]}"
    return 0
}

# Checks that a mapping is complete enough to touch the network or data.
configValidateOperational() {
    local name="$1" dest="${mapDest[$1]}" source="${mapSource[$1]}" root rootKey command found=0
    if [[ -n "${mapUuid[$name]}" ]] && _configIsPlaceholder "${mapUuid[$name]}"; then
        _configProblem "uuid for $name is not configured: '${mapUuid[$name]}'"
        return 1
    fi
    if [[ "${mapTarget[$name]}" == local ]]; then
        _configValidateLocal || return 1
        root="$localMount" rootKey="localDestination.mount"
    else
        if [[ -z "$remoteHost" ]]; then
            _configProblem "remoteHost is empty"
            return 1
        fi
        if _configIsPlaceholder "$destinationMount" || [[ "$destinationMount" != /* ]]; then
            _configProblem "destinationMount is not configured: '$destinationMount'"
            return 1
        fi
        root="$destinationMount" rootKey="destinationMount"
    fi
    if _configIsPlaceholder "$dest" || [[ "$dest" != /* ]]; then
        _configProblem "destination for $name is not configured: '$dest'"
        return 1
    fi
    if [[ "$dest" != "${root%/}/"* || "$dest" == *"/../"* || "$dest" == *"/.." ]]; then
        _configProblem "destination for $name must be inside $rootKey ($root): $dest"
        return 1
    fi
    # A local copy into or out of its own source tree would loop or overwrite.
    if [[ "${mapTarget[$name]}" == local && ("$dest" == "$source" || "$dest" == "$source"/* || "$source" == "$dest"/*) ]]; then
        _configProblem "destination for $name overlaps its source: $dest"
        return 1
    fi
    if [[ ! "$minFreeBytesAfter" =~ ^[0-9]+$ ]]; then
        _configProblem "minFreeBytesAfter must be a whole number of bytes"
        return 1
    fi
    for command in "${checksumCommands[@]}"; do
        [[ "$checksumCommand" == "$command" ]] && found=1
    done
    if ((found == 0)); then
        _configProblem "checksum must be one of: ${checksumCommands[*]}"
        return 1
    fi
}

# Two mappings must never claim the same data: a source nested inside another
# mapping's source must be excluded (by top-level name) from the outer one.
_configOverlapCheck() {
    local outer inner relative first
    for outer in "${mappingNames[@]}"; do
        for inner in "${mappingNames[@]}"; do
            [[ "$outer" != "$inner" ]] || continue
            if [[ "${mapSource[$inner]}" == "${mapSource[$outer]}" ]]; then
                log_error "mappings $outer and $inner have the same source: ${mapSource[$outer]}"
                return 1
            fi
            [[ "${mapSource[$inner]}" == "${mapSource[$outer]}"/* ]] || continue
            relative="${mapSource[$inner]#"${mapSource[$outer]}"/}"
            first="${relative%%/*}"
            if [[ "/${mapExcludes[$outer]}/" != *"/$first/"* ]]; then
                log_error "mapping $inner overlaps $outer; add \"$first\" to the excludes of $outer"
                return 1
            fi
        done
    done
}

_configIsPlaceholder() {
    [[ -z "$1" || "$1" == *"<"* || "$1" == *">"* ]]
}

_configProblem() {
    configProblem="$1"
    log_error "$1"
}

# The local destination must be positively identified, so an empty
# mount-point directory or another disk can never receive the copy: by its
# filesystem UUID, or by its mount source for a filesystem without one (a
# mergerFS pool).
_configValidateLocal() {
    if _configIsPlaceholder "$localMount" || [[ "$localMount" != /?* ]]; then
        _configProblem "localDestination.mount is not configured: '$localMount'"
        return 1
    fi
    if [[ -z "$localUuid" && -z "$localSource" ]]; then
        _configProblem "localDestination.uuid (or .source for a filesystem without a UUID) is not configured"
        return 1
    fi
    if [[ -n "$localUuid" ]] && _configIsPlaceholder "$localUuid"; then
        _configProblem "localDestination.uuid is not configured: '$localUuid'"
        return 1
    fi
    if [[ -n "$localSource" ]] && _configIsPlaceholder "$localSource"; then
        _configProblem "localDestination.source is not configured: '$localSource'"
        return 1
    fi
}

## manifest

# Compares a left manifest (normally the source) with a right manifest
# (normally the destination). Writes <prefix>.missing (NUL list of paths absent
# on the right), <prefix>.files (NUL list of matching regular files),
# <prefix>.conflicts and <prefix>.unsupported (readable reports).
manifestCompare() {
    local left="$1" right="$2" prefix="$3"
    local -A rightEntries=()
    local record rType rSize rMtime
    cmpBytes=0 cmpConflicts=0 cmpDirs=0 cmpFiles=0 cmpIdentical=0
    cmpMissing=0 cmpMissingBytes=0 cmpMissingDirs=0 cmpMissingFiles=0 cmpUnsupported=0
    : >"$prefix.missing"
    : >"$prefix.files"
    : >"$prefix.conflicts"
    : >"$prefix.unsupported"

    while IFS= read -r -d '' record; do
        _manifestRecordSplit "$record"
        rightEntries["$_path"]="$_type"$'\t'"$_size"$'\t'"$_mtime"
    done <"$right"

    while IFS= read -r -d '' record; do
        _manifestRecordSplit "$record"
        case "$_type" in
            f) cmpFiles=$((cmpFiles + 1)); cmpBytes=$((cmpBytes + _size)) ;;
            d) cmpDirs=$((cmpDirs + 1)) ;;
            l) ;;
            *)
                cmpUnsupported=$((cmpUnsupported + 1))
                printf '%s\tunsupported type %s\n' "$(_manifestPathShow "$_path")" "$_type" >>"$prefix.unsupported"
                continue
                ;;
        esac
        if [[ -z "${rightEntries[$_path]+x}" ]]; then
            cmpMissing=$((cmpMissing + 1))
            printf '%s\0' "$_path" >>"$prefix.missing"
            if [[ "$_type" == d ]]; then
                cmpMissingDirs=$((cmpMissingDirs + 1))
            else
                cmpMissingFiles=$((cmpMissingFiles + 1))
                cmpMissingBytes=$((cmpMissingBytes + _size))
            fi
            continue
        fi
        IFS=$'\t' read -r rType rSize rMtime <<<"${rightEntries[$_path]}"
        if _manifestEntriesMatch "$_type" "$_size" "$_mtime" "$rType" "$rSize" "$rMtime"; then
            cmpIdentical=$((cmpIdentical + 1))
            [[ "$_type" == f ]] && printf '%s\0' "$_path" >>"$prefix.files"
        else
            cmpConflicts=$((cmpConflicts + 1))
            printf '%s\tsource: %s %s bytes mtime %s\tdestination: %s %s bytes mtime %s\n' \
                "$(_manifestPathShow "$_path")" "$_type" "$_size" "${_mtime%%.*}" \
                "$rType" "$rSize" "${rMtime%%.*}" >>"$prefix.conflicts"
        fi
    done <"$left"
}

manifestFingerprint() {
    sha256sum <"$1" | cut -d' ' -f1
}

# Lists a source tree without crossing into other filesystems. Fails if any
# part of the tree cannot be read, so unreadable data is never treated as
# migrated.
manifestSource() {
    local source="$1" output="$2" mapping="${3:-}" name pruneArgs=() names=()
    if [[ -n "$mapping" ]]; then
        mapfile -t names < <(configMappingExcludes "$mapping")
    else
        names=("${excludeNames[@]}")
    fi
    for name in "${names[@]}"; do
        [[ -n "$name" ]] || continue
        if ((${#pruneArgs[@]} > 0)); then
            pruneArgs+=(-o)
        fi
        pruneArgs+=(-path "./$(_manifestGlobEscape "$name")")
    done
    if ((${#pruneArgs[@]} > 0)); then
        pruneArgs=(\( "${pruneArgs[@]}" \) -prune -o)
    fi
    (
        set -o pipefail
        cd -- "$source" &&
            find . -xdev -mindepth 1 "${pruneArgs[@]}" \
                \( -type d -printf 'd\t0\t0\t%P\0' \) -o -printf '%y\t%s\t%T@\t%P\0' |
            LC_ALL=C sort -z
    ) >"$output"
}

_manifestEntriesMatch() {
    local type="$1" size="$2" mtime="$3" rType="$4" rSize="$5" rMtime="$6"
    [[ "$type" == "$rType" ]] || return 1
    case "$type" in
        d) return 0 ;;
        l) [[ "$size" == "$rSize" ]] ;;
        *) [[ "$size" == "$rSize" && "${mtime%%.*}" == "${rMtime%%.*}" ]] ;;
    esac
}

_manifestGlobEscape() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\*/\\*}"
    value="${value//\?/\\?}"
    value="${value//\[/\\[}"
    printf '%s' "$value"
}

_manifestPathShow() {
    local path="$1"
    path="${path//$'\n'/\\n}"
    printf '%s' "${path//$'\t'/\\t}"
}

_manifestRecordSplit() {
    local rest
    _type="${1%%$'\t'*}"
    rest="${1#*$'\t'}"
    _size="${rest%%$'\t'*}"
    rest="${rest#*$'\t'}"
    _mtime="${rest%%$'\t'*}"
    _path="${rest#*$'\t'}"
}

## state

stateFile() {
    printf '%s/%s.state' "$stateDir" "$1"
}

stateGet() {
    printf '%s' "${state[$1]:-${2:-}}"
}

stateHistoryAppend() {
    local name="$1" event="$2" detail="${3:-}"
    printf '%s\t%s\t%s\n' "$(date -Is)" "$event" "${detail//$'\n'/ }" >>"$stateDir/$name.history"
}

stateLoad() {
    local name="$1" file key value
    file="$(stateFile "$name")"
    state=()
    [[ -f "$file" ]] || return 0
    while IFS= read -r key; do
        [[ "$key" == *=* ]] || continue
        value="${key#*=}"
        key="${key%%=*}"
        [[ "$key" =~ ^[A-Za-z]+$ ]] && state[$key]="$value"
    done <"$file"
}

# Updates keys in the loaded state and writes it atomically.
stateSave() {
    local name="$1" pair key file temp value
    shift
    for pair in "$@"; do
        key="${pair%%=*}"
        state[$key]="${pair#*=}"
    done
    state[name]="$name"
    state[updated]="$(date -Is)"
    file="$(stateFile "$name")"
    temp="$file.tmp.$$"
    for key in $(printf '%s\n' "${!state[@]}" | LC_ALL=C sort); do
        value="${state[$key]//$'\n'/ }"
        printf '%s=%s\n' "$key" "$value"
    done >"$temp"
    mv -f -- "$temp" "$file"
}
