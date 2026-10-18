#!/usr/bin/env bash
# migrateToRaid workflow: copy andy-pc storage to raid-pc, verify it
# independently, record the result, and remove source data only when
# explicitly requested and proven safe. Not a bootstrap module; sourced by
# migrateToRaid.sh.
#
#   COPY -> VERIFY -> RECORD -> (explicit, separate) REMOVE SOURCE

_raidMigrationDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/raidMigrationStore.sh
source "$_raidMigrationDir/raidMigrationStore.sh"
# shellcheck source=lib/raidMigrationRemote.sh
source "$_raidMigrationDir/raidMigrationRemote.sh"

action="migrate"
applicationName="migrateToRaid"
configOverride=""
dryRun=1
lockFd=""
maxCopyPasses=3
selectAll=0
selectSources=()
selectTypes=()
selectedNames=()
verbose=0
verifyLevel="quick"
workDir=""
yesDelete=0
_activeName=""

raidMigrationMain() {
    local status=0
    argsParse "$@"
    stateDir="${XDG_STATE_HOME:-$HOME/.local/state}/$applicationName"
    mkdir -p "$stateDir"
    chmod 700 "$stateDir" 2>/dev/null || true
    loggingInitialize
    commandsRequire
    configLoad "${configOverride:-${XDG_CONFIG_HOME:-$HOME/.config}/$applicationName/config.json}" || exit 1
    selectionResolve || exit 2
    remoteTarget="$remoteHost"
    [[ -n "$remoteUser" ]] && remoteTarget="$remoteUser@$remoteHost"
    workDir="$(mktemp -d "${TMPDIR:-/tmp}/$applicationName.XXXXXX")"
    trap '_raidCleanup' EXIT
    trap '_raidInterrupted' INT TERM
    case "$action" in
        status) statusShow || status=$? ;;
        check) checkSelected || status=$? ;;
        remove) removeSelected || status=$? ;;
        *) migrateSelected || status=$? ;;
    esac
    exit "$status"
}

## args

argsParse() {
    local actions=0
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -y | --confirm) dryRun="" ;;
            --all) selectAll=1 ;;
            --check)
                action=check
                actions=$((actions + 1))
                if [[ -n "${2:-}" && "$2" != -* ]]; then
                    selectSources+=("$2")
                    shift
                fi
                ;;
            --config)
                _argumentRequireValue "$1" "${2:-}"
                configOverride="$2"
                shift
                ;;
            --remove-source) action=remove; actions=$((actions + 1)) ;;
            --source)
                _argumentRequireValue "$1" "${2:-}"
                selectSources+=("$2")
                shift
                ;;
            --status) action=status; actions=$((actions + 1)) ;;
            --type)
                _argumentRequireValue "$1" "${2:-}"
                selectTypes+=("${2,,}")
                shift
                ;;
            --verbose) verbose=1 ;;
            --verify)
                _argumentRequireValue "$1" "${2:-}"
                if [[ "$2" != quick && "$2" != full ]]; then
                    echo "ERROR: --verify must be quick or full" >&2
                    exit 2
                fi
                verifyLevel="$2"
                shift
                ;;
            --verify-only) action=verify; actions=$((actions + 1)) ;;
            --yes-delete) yesDelete=1 ;;
            -h | --help)
                argsUsage
                exit 0
                ;;
            *)
                echo "ERROR: unknown argument: $1" >&2
                argsUsage >&2
                exit 2
                ;;
        esac
        shift
    done
    if ((actions > 1)); then
        echo "ERROR: choose only one of --status, --check, --verify-only, --remove-source" >&2
        exit 2
    fi
    if ((yesDelete == 1)) && [[ "$action" != remove ]]; then
        echo "ERROR: --yes-delete is only valid with --remove-source" >&2
        exit 2
    fi
}

argsUsage() {
    cat <<'EOF'
Usage: migrateToRaid [--all | --source NAME ... | --type TYPE ...] [options]

Copy andy-pc storage to raid-pc, verify it, and record the result.
Preview only unless --confirm is given. Source data is never removed
unless --remove-source is requested separately.

Selection:
  --all                 Every enabled mapping
  --source NAME         One mapping by name or source path (repeatable)
  --type TYPE           Enabled mappings of a type, e.g. movies (repeatable)

Migration:
  -y, --confirm         Copy and verify (default is a read-only preview)
  --verify LEVEL        quick (size + mtime, default) or full (checksums)
  --verify-only         Verify an already copied mapping without copying
  --verbose             Show every transferred file

Reporting:
  --status              Show recorded state of every mapping
  --check [NAME]        Report SAFE / NOT SAFE TO REMOVE DISK

Source removal:
  --remove-source       Delete migrated source content for one --source
                        (preview unless --confirm; asks for confirmation)
  --yes-delete          Skip the typed deletion confirmation

Other:
  --config FILE         Configuration (default ~/.config/migrateToRaid/config.json)
  -h, --help            Show this help
EOF
}

## check

# Reports whether a mapping's disk is safe to remove. COPY VERIFIED requires
# a full checksum verification of the source that is mounted now, with no
# change since. SAFE TO REMOVE additionally requires raid-pc protection.
checkMapping() {
    local name="$1" source="${mapSource[$1]}" dest="${mapDest[$1]}" prefix="$workDir/$1.check"
    local removed copyVerified=1
    checkReasons=()
    _say ""
    _say "${mapLabel[$name]} ($name)"
    _sayField "Source:" "$source"
    _sayField "Destination:" "$remoteTarget:$dest"
    stateLoad "$name"
    removed="$(stateGet sourceRemoved no)"

    if [[ -z "$(stateGet sourceUuid)" ]]; then
        _checkResult fail "no confirmed migration has been recorded"
        copyVerified=0
    elif ! sourceInspect "$name"; then
        _checkResult fail "$sourceProblem"
        copyVerified=0
    elif ! identityCheck "$name"; then
        _checkResult fail "$sourceProblem"
        copyVerified=0
    else
        _checkResult ok "mounted filesystem is the one migrated ($srcFsType UUID $srcUuid)"
    fi
    _checkStateItems "$name" || copyVerified=0
    if ((copyVerified == 1)); then
        _checkSourceUnchanged "$name" "$prefix" "$removed" || copyVerified=0
        _checkDestination "$name" "$prefix" || copyVerified=0
    fi
    if protectionCheck; then
        _checkResult ok "$protectionName is established and in sync"
    else
        _checkResult fail "$protectionProblem"
    fi

    _say ""
    if ((copyVerified == 1)); then
        _say "COPY VERIFIED"
    else
        _say "COPY NOT VERIFIED"
    fi
    if ((copyVerified == 1)) && [[ "$protectionResult" == ok ]]; then
        _say "SAFE TO REMOVE $(_checkSubject "$name")"
        stateSave "$name" lastCheck="$(date -Is)" lastCheckResult=safe
        return 0
    fi
    _say "NOT SAFE TO REMOVE $(_checkSubject "$name")"
    local reason
    for reason in "${checkReasons[@]}"; do
        _say "  - $reason"
    done
    if [[ -n "$(stateGet sourceUuid)" ]]; then
        if ((copyVerified == 1)); then
            stateSave "$name" lastCheck="$(date -Is)" lastCheckResult=copyVerified
        else
            stateSave "$name" lastCheck="$(date -Is)" lastCheckResult=notSafe
        fi
    fi
    return 1
}

# Checks the selected mappings. When a mapping covers only part of a disk,
# every other mapping on that disk is checked too and a disk verdict follows.
checkSelected() {
    local name other mount status=0 mounts=()
    local -A checked=() safe=()
    for name in "${selectedNames[@]}"; do
        _checkCoversDisk "$name" || _listAdd mounts "${mapMount[$name]}"
    done
    for name in "${selectedNames[@]}"; do
        checked[$name]=1
        if checkMapping "$name"; then safe[$name]=1; else status=1; fi
    done
    for mount in "${mounts[@]}"; do
        for other in "${mappingNames[@]}"; do
            [[ "${mapMount[$other]}" == "$mount" && -z "${checked[$other]:-}" ]] || continue
            checked[$other]=1
            checkMapping "$other" && safe[$other]=1
        done
        _checkDisk "$mount" safe || status=1
    done
    return "$status"
}

_checkCoversDisk() {
    [[ "${mapSource[$1]}" == "${mapMount[$1]}" && -z "${mapExcludes[$1]}" ]]
}

# A disk is safe only when every mapping on it is safe and every top-level
# entry on it belongs to one of those mappings.
_checkDisk() {
    local mount="$1" name entry covered reasons=() mappings=()
    local -n safeRef="$2"
    for name in "${mappingNames[@]}"; do
        [[ "${mapMount[$name]}" == "$mount" ]] || continue
        mappings+=("$name")
        [[ -n "${safeRef[$name]:-}" ]] || reasons+=("mapping $name is not safe to remove")
    done
    if ! findmnt -n --mountpoint "$mount" >/dev/null 2>&1; then
        reasons+=("no filesystem is mounted at $mount")
    else
        while IFS= read -r -d '' entry; do
            _listContains excludeNames "$entry" && continue
            covered=0
            for name in "${mappings[@]}"; do
                if [[ "${mapSource[$name]}" == "$mount" && "/${mapExcludes[$name]}/" != *"/$entry/"* ]] ||
                    [[ "${mapSource[$name]}" == "$mount/$entry" ]]; then
                    covered=1
                fi
            done
            ((covered == 1)) || reasons+=("$mount/$(_manifestPathShow "$entry") is not covered by any mapping")
        done < <(find "$mount" -mindepth 1 -maxdepth 1 -printf '%f\0' 2>/dev/null | LC_ALL=C sort -z)
    fi
    _say ""
    _say "Disk $mount (mappings: ${mappings[*]})"
    if ((${#reasons[@]} == 0)); then
        _say "SAFE TO REMOVE DISK"
        return 0
    fi
    _say "NOT SAFE TO REMOVE DISK"
    for entry in "${reasons[@]}"; do
        _say "  - $entry"
    done
    return 1
}

_checkSubject() {
    if _checkCoversDisk "$1"; then
        printf 'DISK'
    else
        printf 'SOURCE FOLDER'
    fi
}

_checkDestination() {
    local name="$1" prefix="$2" dest="${mapDest[$1]}"
    if ! configValidateOperational "$name"; then
        _checkResult fail "$configProblem"
        return 1
    fi
    if ! remoteProbe "$dest"; then
        _checkResult fail "raid-pc is not reachable over SSH: $probeError"
        return 1
    fi
    if [[ "$probeMounted" != yes ]]; then
        _checkResult fail "raid-pc storage is not mounted at $destinationMount"
        return 1
    fi
    if ! remoteManifest "$dest" "$prefix.dest"; then
        _checkResult fail "could not list the destination on raid-pc"
        return 1
    fi
    manifestCompare "$stateDir/$name.manifest" "$prefix.dest" "$prefix.destCompare"
    if ((cmpMissing > 0 || cmpConflicts > 0)); then
        _checkResult fail "destination no longer matches the verified manifest ($cmpMissing missing, $cmpConflicts changed)"
        return 1
    fi
    _checkResult ok "destination is reachable and still matches the verified manifest"
}

_checkResult() {
    if [[ "$1" == ok ]]; then
        _say "  [ok]   $2"
    else
        _say "  [FAIL] $2"
        checkReasons+=("$2")
    fi
}

# The verified manifest proves nothing on its own: rescan the mounted source.
_checkSourceUnchanged() {
    local name="$1" prefix="$2" removed="$3"
    if ! manifestSource "${mapSource[$name]}" "$prefix.source" "$name" 2>"$prefix.source.err"; then
        _checkResult fail "could not read the complete source tree: $(tail -n 1 "$prefix.source.err")"
        return 1
    fi
    if [[ "$removed" == no ]]; then
        if [[ "$(manifestFingerprint "$prefix.source")" != "$(stateGet verifiedFingerprint)" ]]; then
            _checkResult fail "source has changed since it was verified; run the migration and verification again"
            return 1
        fi
        _checkResult ok "source content is unchanged since verification"
        return 0
    fi
    manifestCompare "$prefix.source" "$stateDir/$name.manifest" "$prefix.sourceCompare"
    if ((cmpMissing > 0 || cmpConflicts > 0 || cmpUnsupported > 0)); then
        _checkResult fail "source contains data that was not verified ($cmpMissing new, $cmpConflicts changed)"
        return 1
    fi
    _checkResult ok "source holds no unverified data (migrated content removal: $removed)"
}

_checkStateItems() {
    local name="$1" result=0
    if [[ "$(stateGet copyStatus)" == complete ]]; then
        _checkResult ok "copy completed $(stateGet copyCompleted)"
    else
        _checkResult fail "copy is not complete (status: $(stateGet copyStatus 'not run'))"
        result=1
    fi
    if [[ "$(stateGet verifyStatus)" != verified ]]; then
        _checkResult fail "verification has not succeeded (status: $(stateGet verifyStatus pending))"
        result=1
    elif [[ "$(stateGet verifyLevel)" != full ]]; then
        _checkResult fail "only quick verification is recorded; a full checksum verification is required"
        result=1
    else
        _checkResult ok "full checksum verification completed $(stateGet verifyCompleted)"
    fi
    if [[ "$(stateGet conflicts 0)" != 0 ]]; then
        _checkResult fail "$(stateGet conflicts) conflicting destination files need review"
        result=1
    fi
    if [[ ! -f "$stateDir/$name.manifest" ]]; then
        _checkResult fail "verified manifest is missing: $stateDir/$name.manifest"
        result=1
    fi
    return "$result"
}

## identity

# The persisted filesystem identity stops a different disk mounted at the same
# path from inheriting this mapping's migration state.
identityCheck() {
    local name="$1" recordedUuid recordedMount
    recordedUuid="$(stateGet sourceUuid)"
    recordedMount="$(stateGet sourceMount)"
    [[ -z "$recordedUuid" ]] && return 0
    if [[ "$recordedUuid" != "$srcUuid" || "$recordedMount" != "${mapMount[$name]}" ]]; then
        sourceProblem="the filesystem at ${mapMount[$name]} (UUID $srcUuid) is not the one migrated (UUID $recordedUuid at $recordedMount)"
        return 1
    fi
}

## migrate

migrateSelected() {
    local name status=0 results=()
    if [[ -z "${dryRun:-}" || "$action" == verify ]]; then
        _lockAcquire || return 1
    fi
    for name in "${selectedNames[@]}"; do
        if mappingProcess "$name"; then
            results+=("$name|ok")
        else
            results+=("$name|failed")
            status=1
        fi
        _activeName=""
    done
    _migrateSummary "${results[@]}"
    return "$status"
}

mappingProcess() {
    local name="$1" source="${mapSource[$1]}" dest="${mapDest[$1]}" prefix="$workDir/$1"
    _activeName="$name"
    stateLoad "$name"
    _say ""
    _say "${mapLabel[$name]} ($name, ${mapType[$name]})"
    _sayField "Source:" "$source"
    _sayField "Destination:" "$remoteTarget:$dest"
    configValidateOperational "$name" || { _mappingFail "$name" "$configProblem"; return 1; }
    sourceInspect "$name" || { _mappingFail "$name" "$sourceProblem"; return 1; }
    identityCheck "$name" || { _mappingFail "$name" "$sourceProblem"; return 1; }
    _sayField "Filesystem:" "$srcFsType UUID $srcUuid ($srcDevice)"
    _mappingPreflightRemote "$name" || return 1
    _mappingScan "$name" "$prefix" || return 1
    _mappingReport "$name" "$prefix"
    if ((cmpUnsupported > 0)); then
        _mappingFail "$name" "$cmpUnsupported unsupported entries (sockets, devices, pipes) cannot be migrated; see $(_mappingSaveReport "$name" "$prefix.unsupported" unsupported)"
        return 1
    fi
    if [[ "$action" == verify ]]; then
        if [[ "$(stateGet copyStatus)" != complete ]]; then
            _mappingFail "$name" "copy is not complete (status: $(stateGet copyStatus 'not run')); run with --confirm"
            return 1
        fi
        _mappingVerify "$name" "$prefix"
        return
    fi
    _mappingSpaceCheck "$name" || return 1
    if [[ -n "${dryRun:-}" ]]; then
        transferArgsBuild "<files-to-copy list>" "$srcFsType" "$stateDir/$name-<timestamp>.rsync.log"
        _say "  rsync:"
        _say "    $(transferDescribe "$source" "$dest")"
        _say "  Preview only: nothing was changed. Re-run with --confirm to copy and verify."
        return 0
    fi
    stateSave "$name" sourceUuid="$srcUuid" sourceMount="${mapMount[$name]}" sourcePath="$source" sourceFsType="$srcFsType" \
        sourceDevice="$srcDevice" destination="$remoteTarget:$dest" copyStatus=running \
        copyStarted="$(date -Is)" copyCompleted="" verifyStatus=pending pid="$$" lastError=""
    stateHistoryAppend "$name" copyStarted "missing=$cmpMissing conflicts=$cmpConflicts"
    _mappingCopy "$name" "$prefix" || return 1
    _mappingVerify "$name" "$prefix"
}

_mappingCopy() {
    local name="$1" prefix="$2" source="${mapSource[$1]}" dest="${mapDest[$1]}"
    local pass=1 copiedFiles=0 copiedBytes=0 rsyncLog detail
    while ((cmpMissing > 0)); do
        if ((pass > maxCopyPasses)); then
            _mappingFail "$name" "source is still changing: $cmpMissing new entries after $maxCopyPasses copy passes" copyStatus=partial
            return 1
        fi
        if [[ "$probeDestExists" != yes ]] && ! remoteMakeDirectory "$dest"; then
            _mappingFail "$name" "could not create destination on raid-pc: $dest" copyStatus=failed
            return 1
        fi
        probeDestExists=yes
        _say "  Copying (pass $pass): $cmpMissingFiles files, $cmpMissingDirs directories, $(_bytesFormat "$cmpMissingBytes")"
        rsyncLog="$stateDir/$name-$(date +%Y%m%d-%H%M%S).rsync.log"
        transferArgsBuild "$prefix.missing" "$srcFsType" "$rsyncLog"
        log_value "rsync log" "$rsyncLog"
        transferRun "$source" "$dest" "$prefix.rsync.out" "$prefix.rsync.err" "$prefix.rsync.status"
        copiedFiles=$((copiedFiles + transferFiles))
        copiedBytes=$((copiedBytes + transferBytes))
        stateSave "$name" copiedFiles="$copiedFiles" copiedBytes="$copiedBytes"
        if [[ "$transferStatus" != 0 ]]; then
            detail="$(tail -n 2 "$prefix.rsync.err" | tr '\n' ' ')"
            _mappingFail "$name" "rsync exit $transferStatus ($(transferStatusExplain "$transferStatus")): $detail; re-run to resume" copyStatus=partial
            return 1
        fi
        _say "  Copied $transferFiles files ($(_bytesFormat "$transferBytes")); re-scanning both sides"
        _mappingScan "$name" "$prefix" || return 1
        pass=$((pass + 1))
    done
    if ((cmpConflicts > 0)); then
        _mappingFail "$name" "$cmpConflicts destination files differ from the source and were not overwritten; review $(_mappingSaveReport "$name" "$prefix.conflicts" conflicts)" \
            copyStatus=conflicts conflicts="$cmpConflicts"
        return 1
    fi
    stateSave "$name" copyStatus=complete copyCompleted="$(date -Is)" conflicts=0 \
        sourceFiles="$cmpFiles" sourceBytes="$cmpBytes"
    stateHistoryAppend "$name" copyComplete "files=$copiedFiles bytes=$copiedBytes"
    _say "  Copy complete"
}

# Records a failure. Preview runs never write state.
_mappingFail() {
    local name="$1" message="$2"
    shift 2
    progressFinish
    log_error "$name: $message"
    if [[ -z "${dryRun:-}" || "$action" == verify ]] && [[ -n "$(stateGet sourceUuid)" ]]; then
        stateSave "$name" lastError="$message" "$@"
        stateHistoryAppend "$name" failed "$message"
    fi
    return 1
}

_mappingPreflightRemote() {
    local name="$1" dest="${mapDest[$1]}"
    if ! remoteProbe "$dest"; then
        _sayField "Reachable:" "no"
        _mappingFail "$name" "raid-pc is not reachable over SSH as $remoteTarget: $probeError"
        return 1
    fi
    [[ -n "$probeRsync" ]] || { _mappingFail "$name" "rsync is not installed on raid-pc"; return 1; }
    [[ "$probeChecksum" == yes ]] || { _mappingFail "$name" "$checksumCommand is not available on raid-pc"; return 1; }
    _sayField "Reachable:" "yes ($probeRsync)"
    if [[ "$probeMounted" != yes ]]; then
        _mappingFail "$name" "raid-pc storage is not mounted at $destinationMount"
        return 1
    fi
    if [[ -n "$destinationFsType" && "$probeMountFsType" != "$destinationFsType" ]]; then
        _mappingFail "$name" "raid-pc $destinationMount is $probeMountFsType, expected $destinationFsType"
        return 1
    fi
    if [[ "${probeFsTarget%"${probeFsTarget##*[![:space:]]}"}" != "$destinationMount" ]]; then
        _mappingFail "$name" "destination would be created outside $destinationMount (on ${probeFsTarget:-unknown}); refusing"
        return 1
    fi
    if [[ "$probeWritable" != yes ]]; then
        _mappingFail "$name" "destination is not writable on raid-pc: $probeAncestor"
        return 1
    fi
    if [[ "$probeDestExists" != yes ]]; then
        _sayField "" "(destination does not exist yet; it will be created inside $probeAncestor)"
    fi
}

_mappingReport() {
    local name="$1" prefix="$2"
    _sayField "Size:" "$(_bytesFormat "$cmpBytes") in $cmpFiles files, $cmpDirs directories"
    _sayField "Available:" "$(_bytesFormat "${probeAvail:-0}") on raid-pc"
    _sayField "On raid-pc:" "$cmpIdentical entries already identical (skipped)"
    _sayField "To copy:" "$cmpMissingFiles files, $cmpMissingDirs directories ($(_bytesFormat "$cmpMissingBytes"))"
    _sayField "Conflicts:" "$cmpConflicts (existing destination files that differ; never overwritten)"
    if ((cmpConflicts > 0)); then
        _reportExcerpt "$prefix.conflicts"
    fi
    if ((verbose == 1 && cmpMissing > 0)); then
        _say "  Entries to copy:"
        tr '\0' '\n' <"$prefix.missing" | sed 's/^/    /' | _sayStream
    fi
}

_mappingSaveReport() {
    local name="$1" report="$2" kind="$3" target
    target="$stateDir/$name.$kind"
    if [[ -n "${dryRun:-}" && "$action" != verify ]]; then
        printf '%s' "$report"
        return
    fi
    cp -f -- "$report" "$target"
    printf '%s' "$target"
}

# Builds fresh manifests of both sides and classifies every source entry as
# missing (eligible to copy), identical (skip) or conflicting (never touched).
_mappingScan() {
    local name="$1" prefix="$2"
    if ! manifestSource "${mapSource[$name]}" "$prefix.source" "$name" 2>"$prefix.source.err"; then
        _mappingFail "$name" "could not read the complete source tree: $(tail -n 1 "$prefix.source.err")"
        return 1
    fi
    if ! remoteManifest "${mapDest[$name]}" "$prefix.dest"; then
        _mappingFail "$name" "could not list the destination on raid-pc: $(tail -n 1 "$prefix.dest.err")"
        return 1
    fi
    manifestCompare "$prefix.source" "$prefix.dest" "$prefix"
}

_mappingSpaceCheck() {
    local name="$1" required
    required=$((cmpMissingBytes + minFreeBytesAfter))
    if [[ ! "$probeAvail" =~ ^[0-9]+$ ]]; then
        _mappingFail "$name" "could not determine free space on raid-pc"
        return 1
    fi
    if ((required > probeAvail)); then
        _mappingFail "$name" "insufficient space on raid-pc: need $(_bytesFormat "$cmpMissingBytes") plus $(_bytesFormat "$minFreeBytesAfter") reserve, $(_bytesFormat "$probeAvail") available"
        return 1
    fi
}

_mappingVerify() {
    local name="$1" prefix="$2" source="${mapSource[$1]}" dest="${mapDest[$1]}"
    stateSave "$name" verifyStatus=running verifyStarted="$(date -Is)" verifyLevel="$verifyLevel" pid="$$"
    if ((cmpMissing > 0 || cmpConflicts > 0)); then
        _mappingFail "$name" "verification failed: $cmpMissing entries missing and $cmpConflicts differing on raid-pc" verifyStatus=failed
        return 1
    fi
    _say "  Quick check: $cmpIdentical entries match (type, size, modification time)"
    if [[ "$verifyLevel" == full ]]; then
        _say "  Verifying checksums ($checksumCommand on both machines)..."
        checksumVerify "$source" "$dest" "$prefix.files" "$prefix"
        if ((checksumMismatches > 0)); then
            _mappingFail "$name" "verification failed: $checksumMismatches files differ by checksum; see $(_mappingSaveReport "$name" "$prefix.checksum-mismatches" checksum-mismatches)" verifyStatus=failed
            return 1
        fi
        _say "  Checksums match for $checksumTotal files"
    fi
    _say "  Final source stability check"
    if ! manifestSource "$source" "$prefix.final" "$name" 2>"$prefix.final.err"; then
        _mappingFail "$name" "could not re-read the source: $(tail -n 1 "$prefix.final.err")" verifyStatus=failed
        return 1
    fi
    if [[ "$(manifestFingerprint "$prefix.final")" != "$(manifestFingerprint "$prefix.source")" ]]; then
        _mappingFail "$name" "source changed during migration/verification; run again to synchronise and re-verify" verifyStatus=failed
        return 1
    fi
    cp -f -- "$prefix.source" "$stateDir/$name.manifest"
    stateSave "$name" verifyStatus=verified verifyLevel="$verifyLevel" verifyCompleted="$(date -Is)" \
        verifiedFingerprint="$(manifestFingerprint "$prefix.source")" verifiedFiles="$cmpFiles" \
        verifiedBytes="$cmpBytes" conflicts=0 lastError=""
    stateHistoryAppend "$name" verified "level=$verifyLevel files=$cmpFiles bytes=$cmpBytes"
    _say ""
    _say "  VERIFIED ($verifyLevel)"
    if [[ "$verifyLevel" == quick ]]; then
        _say "  Quick verification never makes a disk safe to remove; use --verify full."
    fi
}

_migrateSummary() {
    local entry
    _say ""
    _say "Summary"
    for entry in "$@"; do
        _sayField "${entry%%|*}" "${entry#*|}"
    done
    _say "  Mode: $([[ -n "${dryRun:-}" && "$action" != verify ]] && printf 'preview' || printf 'apply')"
    _say "  Log:  $stateDir"
}

## remove

removeSelected() {
    if [[ -z "${dryRun:-}" ]]; then
        _lockAcquire || return 1
    fi
    removeSource "${selectedNames[0]}"
}

# Deletes exactly the verified files, never the mount point, excluded system
# folders, or anything that changed after verification.
removeSource() {
    local name="$1" source="${mapSource[$1]}" files=0 bytes=0 dirs=0 answer record
    if ! checkMapping "$name"; then
        _say ""
        log_error "refusing to remove source data for $name: the disk is not safe to remove"
        return 1
    fi
    if [[ "$(stateGet sourceRemoved no)" == yes ]]; then
        _say "Migrated content has already been removed from $source."
        return 0
    fi
    while IFS= read -r -d '' record; do
        _manifestRecordSplit "$record"
        if [[ "$_type" == d ]]; then
            dirs=$((dirs + 1))
        else
            files=$((files + 1))
            [[ "$_type" == f ]] && bytes=$((bytes + _size))
        fi
    done <"$stateDir/$name.manifest"
    _say ""
    _say "Source removal plan for $source"
    _say "  Delete $files verified files and links ($(_bytesFormat "$bytes"))"
    _say "  Remove up to $dirs directories, only when empty afterwards"
    _say "  Keep the mount point, excluded folders (${excludeNames[*]}) and anything changed since verification"
    if [[ -n "${dryRun:-}" ]]; then
        _say "  Preview only: nothing was deleted. Re-run with --confirm to delete."
        return 0
    fi
    if ((yesDelete == 0)); then
        if [[ ! -t 0 ]]; then
            log_error "deletion needs interactive confirmation; pass --yes-delete to confirm non-interactively"
            return 1
        fi
        read -r -p "Type '$name' to permanently delete this content from $source: " answer
        if [[ "$answer" != "$name" ]]; then
            log_error "confirmation did not match; nothing was deleted"
            return 1
        fi
    fi
    _activeName="$name"
    _removeExecute "$name"
}

_removeExecute() {
    local name="$1" source="${mapSource[$1]}" record path current kept=0 removed=0 dirsRemoved=0
    local removalLog dirList="$workDir/$1.dirs"
    sourceInspect "$name" && identityCheck "$name" || { log_error "$sourceProblem"; return 1; }
    removalLog="$stateDir/$name-$(date +%Y%m%d-%H%M%S).removed"
    stateSave "$name" sourceRemoved=running removalStarted="$(date -Is)" pid="$$"
    stateHistoryAppend "$name" removalStarted "$removalLog"
    : >"$dirList"
    log_action "removing verified content from $source"
    while IFS= read -r -d '' record; do
        _manifestRecordSplit "$record"
        path="$source/$_path"
        case "$_type" in
            d)
                printf '%s\t%s\0' "$(_pathDepth "$_path")" "$_path" >>"$dirList"
                continue
                ;;
            l) [[ -L "$path" ]] || { [[ -e "$path" ]] && kept=$((kept + 1)); continue; } ;;
            f)
                if [[ ! -e "$path" && ! -L "$path" ]]; then
                    continue
                fi
                current="$(stat -c '%s %Y' -- "$path" 2>/dev/null)" || current=""
                if [[ -L "$path" || ! -f "$path" || "$current" != "$_size ${_mtime%%.*}" ]]; then
                    kept=$((kept + 1))
                    printf 'KEPT (changed)\t%s\n' "$(_manifestPathShow "$_path")" >>"$removalLog"
                    continue
                fi
                ;;
        esac
        if rm -f -- "$path"; then
            removed=$((removed + 1))
            printf 'deleted\t%s\n' "$(_manifestPathShow "$_path")" >>"$removalLog"
        else
            kept=$((kept + 1))
        fi
    done <"$stateDir/$name.manifest"
    while IFS= read -r -d '' record; do
        path="$source/${record#*$'\t'}"
        rmdir -- "$path" 2>/dev/null && dirsRemoved=$((dirsRemoved + 1))
    done < <(LC_ALL=C sort -z -t $'\t' -k1,1nr "$dirList")
    if ((kept > 0)); then
        stateSave "$name" sourceRemoved=partial removedFiles="$removed" \
            lastError="$kept entries were kept because they changed or could not be deleted; see $removalLog"
        stateHistoryAppend "$name" removalPartial "removed=$removed kept=$kept"
        log_warn "$kept entries were kept; see $removalLog"
        return 1
    fi
    stateSave "$name" sourceRemoved=yes sourceRemovedAt="$(date -Is)" removedFiles="$removed" lastError=""
    stateHistoryAppend "$name" removalComplete "removed=$removed dirs=$dirsRemoved"
    log_done "removing verified content from $source"
    _say "Removed $removed files/links and $dirsRemoved empty directories. Log: $removalLog"
}

## selection

selectionResolve() {
    local name wanted type found
    selectedNames=()
    if [[ "$action" == remove ]]; then
        if ((selectAll == 1 || ${#selectTypes[@]} > 0 || ${#selectSources[@]} != 1)); then
            log_error "--remove-source requires exactly one --source and no --all or --type"
            return 1
        fi
    fi
    if ((selectAll == 0 && ${#selectSources[@]} == 0 && ${#selectTypes[@]} == 0)); then
        if [[ "$action" == status || "$action" == check ]]; then
            selectedNames=("${mappingNames[@]}")
            return 0
        fi
        log_error "select mappings with --all, --source NAME or --type TYPE"
        return 1
    fi
    for wanted in "${selectSources[@]}"; do
        found=""
        for name in "${mappingNames[@]}"; do
            if [[ "$wanted" == "$name" || "${wanted%/}" == "${mapSource[$name]}" ]]; then
                found="$name"
            fi
        done
        if [[ -z "$found" ]]; then
            log_error "no mapping named '$wanted' in $configFile"
            return 1
        fi
        if [[ "${mapEnabled[$found]}" != true && "$action" != status && "$action" != check ]]; then
            log_error "mapping $found is disabled in $configFile"
            return 1
        fi
        _selectionAdd "$found"
    done
    for name in "${mappingNames[@]}"; do
        [[ "${mapEnabled[$name]}" == true ]] || continue
        if ((selectAll == 1)); then
            _selectionAdd "$name"
            continue
        fi
        for type in "${selectTypes[@]}"; do
            [[ "${mapType[$name]}" == "$type" ]] && _selectionAdd "$name"
        done
    done
    if ((${#selectedNames[@]} == 0)); then
        log_error "no enabled mappings match the selection"
        return 1
    fi
}

_selectionAdd() {
    local existing
    for existing in "${selectedNames[@]}"; do
        [[ "$existing" == "$1" ]] && return 0
    done
    selectedNames+=("$1")
}

## source

# Verifies the source is a genuinely mounted, readable filesystem. An empty
# mount-point directory with nothing mounted is never accepted.
sourceInspect() {
    local name="$1" source="${mapSource[$1]}" mount="${mapMount[$1]}" partUuid containing
    sourceProblem=""
    srcDevice="" srcFsType="" srcUuid=""
    if [[ ! -d "$mount" ]]; then
        sourceProblem="source does not exist: $mount"
        return 1
    fi
    if ! findmnt -n --mountpoint "$mount" >/dev/null 2>&1; then
        sourceProblem="no filesystem is mounted at $mount (refusing to treat the mount-point directory as the source)"
        return 1
    fi
    if [[ ! -e "$source" ]]; then
        sourceProblem="source does not exist: $source"
        return 1
    fi
    if [[ ! -d "$source" ]]; then
        sourceProblem="source is not a directory: $source"
        return 1
    fi
    containing="$(findmnt -n -o TARGET -T "$source" 2>/dev/null | head -n 1)"
    if [[ "${containing%"${containing##*[![:space:]]}"}" != "$mount" ]]; then
        sourceProblem="source $source is not on the filesystem mounted at $mount"
        return 1
    fi
    srcFsType="$(_mountField "$mount" FSTYPE)"
    srcDevice="$(_mountField "$mount" SOURCE)"
    srcUuid="$(_mountField "$mount" UUID)"
    if [[ -z "$srcUuid" ]]; then
        partUuid="$(_mountField "$mount" PARTUUID)"
        [[ -n "$partUuid" ]] && srcUuid="PARTUUID=$partUuid"
    fi
    if [[ -z "$srcUuid" ]]; then
        sourceProblem="cannot determine the filesystem UUID mounted at $mount"
        return 1
    fi
    if [[ -n "${mapUuid[$name]}" && "${mapUuid[$name]}" != "$srcUuid" ]]; then
        sourceProblem="filesystem at $mount has UUID $srcUuid, configuration expects ${mapUuid[$name]}"
        return 1
    fi
    if [[ ! -r "$source" || ! -x "$source" ]]; then
        sourceProblem="source is not readable: $source"
        return 1
    fi
}

_mountField() {
    local value
    value="$(findmnt -n -o "$2" --mountpoint "$1" 2>/dev/null | head -n 1)"
    printf '%s' "${value%"${value##*[![:space:]]}"}"
}

## status

statusShow() {
    local name copy verify removed size check pid migrated=0 remaining=0 unknown=0 used
    _say ""
    _say "$(printf '%-12s %-9s %-12s %-14s %-9s %-14s %10s' Source Type Copy Verify Source 'Last check' Size)"
    _say "$(printf '%.0s-' {1..86})"
    for name in "${selectedNames[@]}"; do
        stateLoad "$name"
        copy="$(stateGet copyStatus 'not run')"
        pid="$(stateGet pid)"
        if [[ "$copy" == running ]] && ! kill -0 "$pid" 2>/dev/null; then
            copy=interrupted
        fi
        verify="$(stateGet verifyStatus -)"
        [[ "$verify" == verified ]] && verify="verified($(stateGet verifyLevel))"
        case "$(stateGet sourceRemoved no)" in
            yes) removed=removed ;;
            partial | running) removed=partial ;;
            *) removed=retained ;;
        esac
        case "$(stateGet lastCheckResult)" in
            safe) check=safe ;;
            copyVerified) check="copy verified" ;;
            notSafe) check="not safe" ;;
            *) check=- ;;
        esac
        size=""
        if [[ "$(stateGet verifyStatus)" == verified ]]; then
            size="$(stateGet verifiedBytes 0)"
            migrated=$((migrated + size))
        elif _checkCoversDisk "$name" && findmnt -n --mountpoint "${mapMount[$name]}" >/dev/null 2>&1; then
            used="$(df -B1 --output=used -- "${mapMount[$name]}" 2>/dev/null | tail -n 1 | tr -d ' ')"
            if [[ "$used" =~ ^[0-9]+$ ]]; then
                size="$used"
                [[ "${mapEnabled[$name]}" == true ]] && remaining=$((remaining + used))
            fi
        fi
        [[ -z "$size" && "${mapEnabled[$name]}" == true ]] && unknown=$((unknown + 1))
        [[ "${mapEnabled[$name]}" == true ]] || copy="$copy*"
        _say "$(printf '%-12s %-9s %-12s %-14s %-9s %-14s %10s' "$name" "${mapType[$name]}" "$copy" \
            "$verify" "$removed" "$check" "$([[ -n "$size" ]] && _bytesFormat "$size" || printf '?')")"
    done
    _say ""
    _say "Migrated:  $(_bytesFormat "$migrated") verified"
    _say "Remaining: $(_bytesFormat "$remaining") used on unverified sources$( ((unknown > 0)) && printf ' (+%s not mounted)' "$unknown")"
    _say "* disabled in configuration"
    if [[ -f "$stateDir/protection.state" ]]; then
        _say "Protection: $(sed -n 's/^result=//p' "$stateDir/protection.state") (checked $(sed -n 's/^checked=//p' "$stateDir/protection.state"))"
    else
        _say "Protection: not checked yet (run --check)"
    fi
}

## utilities

commandsRequire() {
    local command commands=(jq findmnt find sort sha256sum numfmt stat)
    if [[ "$action" != status ]]; then
        commands+=(ssh rsync flock)
    fi
    for command in "${commands[@]}"; do
        command -v "$command" >/dev/null 2>&1 || {
            log_error "required command not found: $command"
            exit 127
        }
    done
}

loggingInitialize() {
    local packageDir logUtils
    if [[ -n "${LOG_UTILS:-}" ]]; then
        logUtils="$LOG_UTILS"
    else
        packageDir="$(python3 -c 'import organiseMyProjects, os; print(os.path.dirname(organiseMyProjects.__file__))')" || {
            echo "ERROR: organiseMyProjects is required" >&2
            exit 127
        }
        logUtils="${packageDir}/logUtils.sh"
    fi
    if [[ ! -f "$logUtils" ]]; then
        echo "ERROR: logUtils.sh not found: $logUtils" >&2
        exit 127
    fi
    # shellcheck source=/dev/null
    source "$logUtils"
    setApplication "$applicationName" "$stateDir"
}

_argumentRequireValue() {
    local option="$1" value="$2"
    if [[ -z "$value" || "$value" == --* ]]; then
        echo "ERROR: $option requires a value" >&2
        exit 2
    fi
}

_bytesFormat() {
    numfmt --to=iec-i --suffix=B --format='%.1f' "${1:-0}" 2>/dev/null || printf '%s bytes' "$1"
}

_listAdd() {
    local -n list="$1"
    _listContains "$1" "$2" || list+=("$2")
}

_listContains() {
    local -n haystack="$1"
    local item
    for item in "${haystack[@]}"; do
        [[ "$item" == "$2" ]] && return 0
    done
    return 1
}

_lockAcquire() {
    exec {lockFd}>"$stateDir/$applicationName.lock"
    if ! flock -n "$lockFd"; then
        log_error "another migrateToRaid run is in progress"
        return 1
    fi
}

_pathDepth() {
    local slashes="${1//[^\/]/}"
    printf '%s' "${#slashes}"
}

_raidCleanup() {
    local jobPids
    jobPids="$(jobs -p)"
    [[ -n "$jobPids" ]] && kill $jobPids 2>/dev/null
    [[ -n "$workDir" && -d "$workDir" ]] && rm -rf -- "$workDir"
    return 0
}

# Leaves resumable state: an interrupted copy is "partial", never complete.
_raidInterrupted() {
    progressFinish
    if [[ -n "$_activeName" ]]; then
        local updates=(lastError="interrupted")
        [[ "$(stateGet copyStatus)" == running ]] && updates+=(copyStatus=partial)
        [[ "$(stateGet verifyStatus)" == running ]] && updates+=(verifyStatus=pending)
        [[ "$(stateGet sourceRemoved)" == running ]] && updates+=(sourceRemoved=partial)
        stateSave "$_activeName" "${updates[@]}"
        stateHistoryAppend "$_activeName" interrupted ""
    fi
    log_error "interrupted; re-run the same command to resume"
    exit 130
}

_reportExcerpt() {
    local limit=10
    ((verbose == 1)) && limit=1000000
    head -n "$limit" "$1" | sed 's/^/    /' | _sayStream
    if (($(wc -l <"$1") > limit)); then
        _say "    ... (more; use --verbose)"
    fi
}

_say() {
    printf '%s\n' "$1"
    if [[ -n "${logFile:-}" && "$logFile" != /dev/null ]]; then
        printf '%s\n' "$1" >>"$logFile"
    fi
}

_sayField() {
    _say "$(printf '  %-13s %s' "$1" "$2")"
}

_sayStream() {
    local line
    while IFS= read -r line; do
        _say "$line"
    done
}
