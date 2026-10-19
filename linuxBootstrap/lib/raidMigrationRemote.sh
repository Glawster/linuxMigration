#!/usr/bin/env bash
# Destination, rsync, checksum and progress helpers for migrateToRaid. A
# destination is raid-pc over SSH (the default) or a disk mounted on andy-pc
# (/mnt/media); both run the same scripts and pass the same checks.
# Sourced by lib/raidMigration.sh; not a bootstrap module.

destFsType=""
destHost=""
destKind=""
destMount=""
destPlace=""
destRsyncPrefix=""
destSource=""
destUuid=""
destinationProblem=""
progressActive=0
protectionBasis=""
protectionDetail=""
protectionProblem=""
protectionResult=""
protectionVerdict=""
remoteTarget=""
rsyncArgs=()
declare -gA _protectionBases=()
declare -gA _protectionDetails=()
declare -gA _protectionProblems=()
declare -gA _protectionResults=()
declare -gA _protectionVerdicts=()
sshOptions=(-o BatchMode=yes -o ConnectTimeout=15 -o ServerAliveInterval=30 -o ServerAliveCountMax=10)

# Destination scripts receive their values as positional arguments; never
# splice paths into script text.
_remoteHashScript='
cd -- "$1" || exit 3
while IFS= read -r -d "" path; do
    if hash=$("$2" <"$path" 2>/dev/null); then hash=${hash%% *}; else hash=ERROR; fi
    printf "%s\t%s\0" "$hash" "$path"
done
'

_remoteManifestScript='
set -o pipefail
[ -e "$1" ] || exit 0
cd -- "$1" || exit 3
find . -mindepth 1 \( -type d -name .rsync-partial -prune \) -o \
    \( -type d -printf "d\t0\t0\t%P\0" \) -o -printf "%y\t%s\t%T@\t%P\0" |
    LC_ALL=C sort -z
'

_remoteProbeScript='
dest=$1 mount=$2 checksum=$3
if command -v rsync >/dev/null 2>&1; then
    echo "rsync=$(rsync --version 2>/dev/null | head -n 1)"
else
    echo "rsync="
fi
if command -v "$checksum" >/dev/null 2>&1; then echo checksum=yes; else echo checksum=no; fi
if findmnt -n --mountpoint "$mount" >/dev/null 2>&1; then echo mounted=yes; else echo mounted=no; fi
echo "mountFsType=$(findmnt -n -o FSTYPE --mountpoint "$mount" 2>/dev/null)"
echo "mountUuid=$(findmnt -n -o UUID --mountpoint "$mount" 2>/dev/null)"
echo "mountSource=$(findmnt -n -o SOURCE --mountpoint "$mount" 2>/dev/null)"
path=$dest
while [ ! -e "$path" ]; do path=$(dirname -- "$path"); done
echo "ancestor=$path"
if [ -d "$dest" ]; then echo destExists=yes; else echo destExists=no; fi
echo "fsTarget=$(findmnt -n -o TARGET -T "$path" 2>/dev/null)"
if [ -d "$path" ] && [ -w "$path" ]; then echo writable=yes; else echo writable=no; fi
echo "avail=$(df -B1 --output=avail -- "$path" 2>/dev/null | tail -n 1 | tr -d " ")"
'

## checksum

# Hashes the listed regular files on both machines at the same time and
# compares the results. Writes mismatches to <prefix>.checksum-mismatches.
checksumVerify() {
    local source="$1" dest="$2" list="$3" prefix="$4"
    local localOut="$prefix.local-hashes" remoteOut="$prefix.remote-hashes" remoteErr="$prefix.remote-hash.err"
    local path hash pid remoteStatus=0 lastShown=0
    checksumDone=0
    checksumMismatches=0
    checksumTotal="$(tr -cd '\0' <"$list" | wc -c)"
    : >"$localOut"
    : >"$prefix.checksum-mismatches"

    destinationRun "$_remoteHashScript" "$dest" "$checksumCommand" <"$list" >"$remoteOut" 2>"$remoteErr" &
    pid=$!
    while IFS= read -r -d '' path; do
        hash="$(_checksumFile "$source/$path")" || hash=ERROR
        printf '%s\t%s\0' "$hash" "$path" >>"$localOut"
        checksumDone=$((checksumDone + 1))
        if ((EPOCHSECONDS != lastShown)); then
            lastShown=$EPOCHSECONDS
            _checksumProgress "$remoteOut"
        fi
    done <"$list"
    while kill -0 "$pid" 2>/dev/null; do
        _checksumProgress "$remoteOut"
        sleep 1
    done
    wait "$pid" || remoteStatus=$?
    _checksumProgress "$remoteOut"
    progressFinish
    if ((remoteStatus != 0)); then
        log_warn "destination checksum pass exited with status $remoteStatus: $(tail -n 3 "$remoteErr" 2>/dev/null)"
    fi
    _checksumCompare "$localOut" "$remoteOut" "$prefix.checksum-mismatches"
}

_checksumCompare() {
    local localOut="$1" remoteOut="$2" report="$3" localRecord remoteRecord
    local localHash localPath remoteHash remotePath fdLocal fdRemote
    exec {fdLocal}<"$localOut" {fdRemote}<"$remoteOut"
    while IFS= read -r -d '' localRecord <&"$fdLocal"; do
        IFS= read -r -d '' remoteRecord <&"$fdRemote" || remoteRecord=$'MISSING\t'
        localHash="${localRecord%%$'\t'*}"
        localPath="${localRecord#*$'\t'}"
        remoteHash="${remoteRecord%%$'\t'*}"
        remotePath="${remoteRecord#*$'\t'}"
        if [[ "$localHash" == ERROR || "$remoteHash" == ERROR || "$remotePath" != "$localPath" || "$localHash" != "$remoteHash" ]]; then
            checksumMismatches=$((checksumMismatches + 1))
            printf '%s\tsource %s\tdestination %s\n' "$(_manifestPathShow "$localPath")" "$localHash" "$remoteHash" >>"$report"
        fi
    done
    exec {fdLocal}<&- {fdRemote}<&-
}

_checksumFile() {
    local output
    output="$("$checksumCommand" <"$1")" || return 1
    printf '%s' "${output%% *}"
}

_checksumProgress() {
    local remoteDone percent=100
    remoteDone="$(tr -cd '\0' <"$1" | wc -c)"
    if ((checksumTotal > 0)); then
        percent=$(((checksumDone + remoteDone) * 100 / (checksumTotal * 2)))
    fi
    progressBar "$percent" "source ${checksumDone}/${checksumTotal}  destination ${remoteDone}/${checksumTotal}"
}

## destination

destinationDescribe() {
    if [[ "$destKind" == local ]]; then
        printf '%s (local)' "$1"
    else
        printf '%s%s' "$destRsyncPrefix" "$1"
    fi
}

destinationMakeDirectory() {
    destinationRun 'mkdir -p -- "$1"' "$1"
}

destinationManifest() {
    destinationRun "$_remoteManifestScript" "$1" >"$2" 2>"$2.err"
}

# Confirms, from the last probe, that the expected filesystem is genuinely
# mounted at the destination mount and that the destination resolves inside
# it, so a copy can never land in an empty mount-point directory on the
# operating-system disk. A local destination must also carry its configured
# UUID or mount source and must not be the source filesystem. Sets
# destinationProblem.
destinationMountCheck() {
    local fsTarget="${probeFsTarget%"${probeFsTarget##*[![:space:]]}"}" where="raid-pc $destMount"
    destinationProblem=""
    [[ "$destKind" == local ]] && where="local destination $destMount"
    if [[ "$probeMounted" != yes ]]; then
        if [[ "$destKind" == local ]]; then
            destinationProblem="no filesystem is mounted at $destMount (refusing to copy into the mount-point directory)"
        else
            destinationProblem="raid-pc storage is not mounted at $destMount"
        fi
    elif [[ -n "$destFsType" && "$probeMountFsType" != "$destFsType" ]]; then
        destinationProblem="$where is $probeMountFsType, expected $destFsType"
    elif [[ -n "$destUuid" && "$probeMountUuid" != "$destUuid" ]]; then
        destinationProblem="$where has UUID ${probeMountUuid:-unknown}, configuration expects $destUuid"
    elif [[ -n "$destSource" && "$probeMountSource" != "$destSource" ]]; then
        destinationProblem="$where is mounted from ${probeMountSource:-unknown}, configuration expects $destSource"
    elif [[ "$destKind" == local && -n "${srcUuid:-}" && "$probeMountUuid" == "$srcUuid" ]]; then
        destinationProblem="$where is the source filesystem (UUID $srcUuid); refusing"
    elif [[ "$destKind" == local && -n "${srcDevice:-}" && "$probeMountSource" == "$srcDevice" ]]; then
        destinationProblem="$where is the source filesystem ($srcDevice); refusing"
    elif [[ "$fsTarget" != "$destMount" ]]; then
        destinationProblem="destination would be created outside $destMount (on ${fsTarget:-unknown}); refusing"
    fi
    [[ -z "$destinationProblem" ]]
}

# Sets probe* globals describing the destination.
destinationProbe() {
    local dest="$1" output key value
    probeAncestor="" probeAvail="" probeChecksum="" probeDestExists="" probeError=""
    probeFsTarget="" probeMounted="" probeMountFsType="" probeMountSource="" probeMountUuid="" probeRsync="" probeWritable=""
    if ! output="$(destinationRun "$_remoteProbeScript" "$dest" "$destMount" "$checksumCommand" 2>&1 </dev/null)"; then
        probeError="$(tail -n 2 <<<"$output" | tr '\n' ' ')"
        return 1
    fi
    while IFS= read -r key; do
        [[ "$key" == *=* ]] || continue
        value="${key#*=}"
        case "${key%%=*}" in
            ancestor) probeAncestor="$value" ;;
            avail) probeAvail="$value" ;;
            checksum) probeChecksum="$value" ;;
            destExists) probeDestExists="$value" ;;
            fsTarget) probeFsTarget="$value" ;;
            mounted) probeMounted="$value" ;;
            mountFsType) probeMountFsType="${value%"${value##*[![:space:]]}"}" ;;
            mountSource) probeMountSource="${value%"${value##*[![:space:]]}"}" ;;
            mountUuid) probeMountUuid="${value%"${value##*[![:space:]]}"}" ;;
            rsync) probeRsync="$value" ;;
            writable) probeWritable="$value" ;;
        esac
    done <<<"$output"
}

# Runs a destination script locally or on raid-pc over SSH.
destinationRun() {
    local script="$1" command arg
    shift
    if [[ "$destKind" == local ]]; then
        bash -c "$script" migrateToRaid "$@"
        return
    fi
    printf -v command 'bash -c %q migrateToRaid' "$script"
    for arg in "$@"; do
        printf -v command '%s %q' "$command" "$arg"
    done
    ssh "${sshOptions[@]}" "$remoteTarget" "$command"
}

# Selects a mapping's destination and sets the dest* globals used by every
# destination helper: raid-pc over SSH unless the mapping targets the local
# destination on this machine.
destinationSelect() {
    if [[ "${mapTarget[$1]}" == local ]]; then
        destKind=local destHost="$(hostname -s 2>/dev/null || printf 'this machine')" destMount="$localMount" destPlace="$localMount"
        destFsType="$localFsType" destSource="$localSource" destUuid="$localUuid" destRsyncPrefix=""
    else
        destKind=remote destHost=raid-pc destMount="$destinationMount" destPlace=raid-pc
        destFsType="$destinationFsType" destSource="" destUuid="" destRsyncPrefix="$remoteTarget:"
    fi
}

## progress

progressBar() {
    [[ -t 2 ]] || return 0
    local percent="$1" detail="${2:-}" width=30 filled bar rest
    ((percent > 100)) && percent=100
    filled=$((percent * width / 100))
    printf -v bar '%*s' "$filled" ''
    printf -v rest '%*s' "$((width - filled))" ''
    printf '\r  [%s%s] %3d%% %s\033[K' "${bar// /=}" "${rest// /-}" "$percent" "$detail" >&2
    progressActive=1
}

progressFinish() {
    if [[ -t 2 ]] && ((progressActive == 1)); then
        printf '\n' >&2
    fi
    progressActive=0
}

# Reads rsync --info=progress2 output. Progress updates become a single bar;
# every other line is kept in outFile (and shown when verbose).
progressRender() {
    local outFile="$1" chunk line
    while IFS= read -r -d $'\r' chunk || [[ -n "$chunk" ]]; do
        while IFS= read -r line; do
            if [[ "$line" =~ ^[[:space:]]*[0-9][0-9,.]*[A-Za-z]?[[:space:]]+([0-9]{1,3})%[[:space:]] ]]; then
                progressBar "${BASH_REMATCH[1]}"
            elif [[ -n "$line" ]]; then
                printf '%s\n' "$line" >>"$outFile"
                if [[ "${verbose:-0}" == 1 ]]; then
                    [[ -t 2 ]] && printf '\r\033[K' >&2
                    printf '    %s\n' "$line"
                fi
            fi
        done <<<"$chunk"
        chunk=""
    done
    progressFinish
}

## protection

# Runs the protection readiness command for the selected destination: on
# raid-pc, for example a SnapRAID "diff" that succeeds only when parity is in
# sync; locally, whatever the owner configured for the local destination. A
# local destination needs no command only when the owner has explicitly
# accepted it as a single authoritative copy with "required": false. Results are cached per destination kind for the rest of
# this run and recorded in protection.state / protection-local.state.
# protectionVerdict names the basis of a SAFE verdict so that verified
# protection and accepted single-copy storage are never confused;
# protectionBasis is protected or singleCopy.
protectionCheck() {
    local kind="$destKind" name="$protectionName" command="$protectionCommand" codes=("${protectionSuccessCodes[@]}")
    local output status=0 code stateName=protection.state
    if [[ "$kind" == local ]]; then
        name="$localProtectionName" command="$localProtectionCommand" codes=("${localProtectionSuccessCodes[@]}")
        stateName=protection-local.state
    fi
    if [[ -n "${_protectionResults[$kind]:-}" ]]; then
        protectionResult="${_protectionResults[$kind]}"
        protectionProblem="${_protectionProblems[$kind]}"
        protectionDetail="${_protectionDetails[$kind]}"
        protectionVerdict="${_protectionVerdicts[$kind]}"
        protectionBasis="${_protectionBases[$kind]}"
        [[ "$protectionResult" == ok ]]
        return
    fi
    protectionProblem=""
    protectionDetail="$name is established and in sync"
    protectionVerdict="${name^^} VERIFIED"
    protectionBasis=protected
    if [[ "$kind" == local && "$localProtectionRequired" == false ]]; then
        protectionDetail="single-copy local storage is accepted for $localMount (localDestination.protection.required is false); it is not backed up or redundant"
        protectionVerdict="DESTINATION ACCEPTED AS AUTHORITATIVE (single copy, not redundant)"
        protectionBasis=singleCopy
    elif _configIsPlaceholder "$command"; then
        if [[ "$kind" == local ]]; then
            protectionProblem="$name check is not configured (localDestination.protection.command)"
        else
            protectionProblem="$name check is not configured (protection.command); parity has not been established"
        fi
    else
        if [[ "$kind" == local ]]; then
            output="$(bash -c "$command" 2>&1 </dev/null)" || status=$?
        else
            output="$(ssh "${sshOptions[@]}" "$remoteTarget" "$command" 2>&1 </dev/null)" || status=$?
        fi
        protectionProblem="$name check failed (exit $status): $(tail -n 1 <<<"$output")"
        for code in "${codes[@]}"; do
            [[ "$status" == "$code" ]] && protectionProblem=""
        done
    fi
    if [[ -z "$protectionProblem" ]]; then
        protectionResult=ok
    else
        protectionResult=failed
    fi
    _protectionResults[$kind]="$protectionResult"
    _protectionProblems[$kind]="$protectionProblem"
    _protectionDetails[$kind]="$protectionDetail"
    _protectionVerdicts[$kind]="$protectionVerdict"
    _protectionBases[$kind]="$protectionBasis"
    printf 'checked=%s\nresult=%s\ndetail=%s\n' "$(date -Is)" "$protectionResult" "${protectionProblem//$'\n'/ }" \
        >"$stateDir/$stateName"
    [[ "$protectionResult" == ok ]]
}

## transfer

transferArgsBuild() {
    local list="$1" fsType="$2" rsyncLog="$3" info=progress2
    [[ "${verbose:-0}" == 1 ]] && info=progress2,name1
    rsyncArgs=(
        --from0
        --files-from="$list"
        --dirs
        --links
        --times
        --ignore-existing
        --partial-dir=.rsync-partial
        --protect-args
        --timeout=300
        --info="$info"
        --stats
        --log-file="$rsyncLog"
        --log-file-format='%i %n%L'
    )
    [[ "$destKind" == local ]] || rsyncArgs+=(-e "ssh ${sshOptions[*]}")
    case "$fsType" in
        ntfs | ntfs3 | fuseblk | vfat | exfat | msdos) rsyncArgs+=(--chmod=D755,F644) ;;
        *) rsyncArgs+=(--perms --hard-links) ;;
    esac
}

transferDescribe() {
    local source="$1" dest="$2"
    printf 'rsync'
    printf ' %q' "${rsyncArgs[@]}" "$source/" "$destRsyncPrefix$dest/"
    printf '\n'
}

# Copies only the listed (missing) paths. Sets transferStatus,
# transferFiles and transferBytes.
transferRun() {
    local source="$1" dest="$2" outFile="$3" errFile="$4" statusFile="$5"
    : >"$outFile"
    {
        if rsync "${rsyncArgs[@]}" "$source/" "$destRsyncPrefix$dest/" 2>"$errFile"; then
            printf '0' >"$statusFile"
        else
            printf '%s' "$?" >"$statusFile"
        fi
    } | progressRender "$outFile"
    transferStatus="$(<"$statusFile")"
    transferFiles="$(sed -n 's/^Number of regular files transferred: //p' "$outFile" | tr -d ',' | tail -n 1)"
    transferBytes="$(sed -n 's/^Total transferred file size: \([0-9,]*\).*/\1/p' "$outFile" | tr -d ',' | tail -n 1)"
    transferFiles="${transferFiles:-0}"
    transferBytes="${transferBytes:-0}"
}

transferStatusExplain() {
    case "$1" in
        0) printf 'success' ;;
        11) printf 'file I/O error (destination full or unwritable?)' ;;
        12) printf 'protocol data stream error (network interrupted?)' ;;
        20) printf 'interrupted by signal' ;;
        23) printf 'partial transfer due to errors' ;;
        24) printf 'source files vanished during transfer' ;;
        30 | 35) printf 'timeout waiting for data (network interrupted?)' ;;
        255) printf 'ssh connection failed' ;;
        *) printf 'rsync error' ;;
    esac
}
