#!/usr/bin/env bash
# Tests for migrateToRaid.sh. Sourced from runTests.sh.
#
# Everything runs inside temporary directories. ssh executes locally, findmnt
# reports sandbox "mounts", df can report a chosen free space and rsync can
# simulate an interrupted transfer; real rsync performs the actual copies.
# No real /mnt source or raid-pc storage is ever touched.
#
# Run only these tests with:  ./tests/migrateToRaidTests.sh

_mtrRealRsync="$(command -v rsync)"
_mtrRealDf="$(command -v df)"

_mtrFakeBin() {
    local fakeBin="$testStateDir/mtr-fake-bin"
    [[ -d "$fakeBin" ]] && { printf '%s' "$fakeBin"; return; }
    mkdir -p "$fakeBin"
    cat >"$fakeBin/ssh" <<'EOF'
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o | -p | -l | -i) shift 2 ;;
        -*) shift ;;
        *) break ;;
    esac
done
host="$1"
shift
if [[ -n "${FAKE_SSH_FAIL:-}" ]]; then
    echo "ssh: Could not resolve hostname $host: Name or service not known" >&2
    exit 255
fi
exec bash -c "$*"
EOF
    cat >"$fakeBin/findmnt" <<'EOF'
#!/usr/bin/env bash
column="" mountpoint="" containing=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -o) column="$2"; shift ;;
        --mountpoint) mountpoint="$2"; shift ;;
        -T) containing="$2"; shift ;;
    esac
    shift
done
best="" bestTarget=""
while IFS='|' read -r target fsType uuid device; do
    [[ -n "$target" ]] || continue
    if [[ -n "$mountpoint" ]]; then
        [[ "$target" == "$mountpoint" ]] && best="$target|$fsType|$uuid|$device"
    elif [[ "$containing/" == "$target"/* && ${#target} -gt ${#bestTarget} ]]; then
        best="$target|$fsType|$uuid|$device"
        bestTarget="$target"
    fi
done <"$FAKE_MOUNTS"
if [[ -z "$best" && -n "$containing" ]]; then
    best="/|ext4|root-uuid|/dev/root"
fi
[[ -n "$best" ]] || exit 1
IFS='|' read -r target fsType uuid device <<<"$best"
case "$column" in
    TARGET) echo "$target" ;;
    FSTYPE) echo "$fsType" ;;
    UUID) echo "$uuid" ;;
    SOURCE) echo "$device" ;;
    PARTUUID) echo "" ;;
    *) echo "$target $device $fsType" ;;
esac
EOF
    cat >"$fakeBin/df" <<EOF
#!/usr/bin/env bash
if [[ -n "\${FAKE_DF_AVAIL:-}" && " \$* " == *" --output=avail "* ]]; then
    printf '   Avail\n%s\n' "\$FAKE_DF_AVAIL"
    exit 0
fi
exec "$_mtrRealDf" "\$@"
EOF
    cat >"$fakeBin/rsync" <<EOF
#!/usr/bin/env bash
realRsync="$_mtrRealRsync"
EOF
    cat >>"$fakeBin/rsync" <<'EOF'
transfer=0
[[ " $* " != *" --server "* && " $* " == *" --files-from="* ]] && transfer=1
if ((transfer == 1)) && [[ -n "${FAKE_RSYNC_INTERRUPT:-}" && -f "$FAKE_RSYNC_INTERRUPT" ]]; then
    rm -f -- "$FAKE_RSYNC_INTERRUPT"
    list=""
    for arg in "$@"; do
        [[ "$arg" == --files-from=* ]] && list="${arg#--files-from=}"
    done
    source="${*: -2:1}"
    dest="${*: -1}"
    dest="${dest#*:}"
    last=""
    while IFS= read -r -d '' path; do
        [[ -f "$source/$path" ]] && last="$path"
    done <"$list"
    if [[ -n "$last" ]]; then
        partialDir="$(dirname -- "$dest/$last")/.rsync-partial"
        mkdir -p -- "$partialDir"
        head -c "$(($(stat -c %s -- "$source/$last") / 2))" -- "$source/$last" >"$partialDir/$(basename -- "$last")"
    fi
    echo "rsync: connection unexpectedly closed (simulated)" >&2
    exit 12
fi
status=0
"$realRsync" "$@" || status=$?
if ((transfer == 1)) && [[ -n "${FAKE_RSYNC_ADD_SOURCE:-}" && ! -e "$FAKE_RSYNC_ADD_SOURCE" ]]; then
    echo "written during migration" >"$FAKE_RSYNC_ADD_SOURCE"
fi
exit "$status"
EOF
    cat >"$fakeBin/fake-protection" <<'EOF'
#!/usr/bin/env bash
exit "${FAKE_PROTECTION_STATUS:-0}"
EOF
    chmod +x "$fakeBin"/*
    printf '%s' "$fakeBin"
}

_mtrLogUtilsStub() {
    local stub="$testStateDir/mtr-logUtils.sh"
    if [[ ! -f "$stub" ]]; then
        cat >"$stub" <<'EOF'
setApplication() { :; }
log_doing() { echo "$1..."; }
log_done() { echo "...$1"; }
log_info() { echo "...$1"; }
log_value() { echo "...$1: $2"; }
log_action() { echo "...$1"; }
log_warn() { echo "WARNING: $1" >&2; }
log_error() { echo "ERROR: $1" >&2; }
EOF
    fi
    printf '%s' "$stub"
}

# Creates a fresh sandbox with one mounted source (movie1), a mounted raid-pc
# storage namespace and a configuration enabling the movie1 mapping.
_mtrSandbox() {
    mtrBox="$(mktemp -d "$testStateDir/mtr.XXXXXX")"
    mtrSource="$mtrBox/mnt/movie1"
    mtrStorage="$mtrBox/raid/storage"
    mtrDest="$mtrStorage/movies/movie1"
    mtrState="$mtrBox/state/migrateToRaid"
    mtrConfig="$mtrBox/config.json"
    mkdir -p "$mtrSource/Films/A Film (2001)" "$mtrSource/lost+found" "$mtrStorage"
    printf 'feature presentation\n%.0s' {1..200} >"$mtrSource/Films/A Film (2001)/A Film (2001).mkv"
    printf 'subtitles\n' >"$mtrSource/Films/A Film (2001)/A Film (2001).en.srt"
    printf 'system\n' >"$mtrSource/lost+found/#123"
    printf '%s|ntfs3|UUID-MOVIE1|/dev/sdx1\n%s|fuse.mergerfs|pool|storage\n' "$mtrSource" "$mtrStorage" >"$mtrBox/mounts"
    cat >"$mtrConfig" <<EOF
{
  "remoteHost": "raid-pc",
  "remoteUser": "",
  "destinationMount": "$mtrStorage",
  "destinationFsType": "fuse.mergerfs",
  "minFreeBytesAfter": 1024,
  "protection": { "name": "SnapRAID parity", "command": "fake-protection", "successExitCodes": [0] },
  "mappings": [
    { "name": "movie1", "label": "Movies 1", "type": "movies", "source": "$mtrSource", "destination": "$mtrDest", "enabled": true },
    { "name": "video1", "label": "TV 1", "type": "tv", "source": "$mtrBox/mnt/video1", "destination": "$mtrStorage/tv/video1", "enabled": false }
  ]
}
EOF
}

# Runs migrateToRaid in the sandbox. Sets mtrOutput and mtrStatus.
_mtrRun() {
    mtrStatus=0
    mtrOutput="$(
        PATH="$(_mtrFakeBin):$PATH" LOG_UTILS="$(_mtrLogUtilsStub)" FAKE_MOUNTS="$mtrBox/mounts" \
            XDG_STATE_HOME="$mtrBox/state" XDG_CONFIG_HOME="$mtrBox/config" \
            "$projectDir/migrateToRaid.sh" --config "$mtrConfig" "$@" 2>&1 </dev/null
    )" || mtrStatus=$?
}

_mtrState() {
    sed -n "s/^$1=//p" "$mtrState/movie1.state" 2>/dev/null
}

_mtrCheck() {
    local description="$1"
    shift
    if "$@"; then
        printf 'PASS  %s\n' "$description"
        ((passed += 1))
    else
        printf 'FAIL  %s\nStatus: %s\nOutput:\n%s\n' "$description" "${mtrStatus:-}" "${mtrOutput:-}"
        ((failed += 1))
    fi
}

_mtrNotContains() {
    [[ "$1" != *"$2"* ]]
}

_mtrSameTree() {
    diff -r --exclude=lost+found "$mtrSource" "$mtrDest" >/dev/null 2>&1
}

## arguments

testMigrateToRaidHelp() {
    local output
    output="$("$projectDir/migrateToRaid.sh" --help)"
    assertContains "$output" '--confirm' 'migrateToRaid help documents --confirm'
    assertContains "$output" '--verify LEVEL' 'migrateToRaid help documents verification levels'
    assertContains "$output" '--check' 'migrateToRaid help documents --check'
    assertContains "$output" '--yes-delete' 'migrateToRaid help documents --yes-delete'
    _mtrCheck 'migrateToRaid help does not expose --dry-run' _mtrNotContains "$output" '--dry-run'
}

testMigrateToRaidArgumentErrors() {
    _mtrSandbox
    _mtrRun --dry-run
    _mtrCheck 'migrateToRaid rejects --dry-run' test "$mtrStatus" -eq 2
    _mtrRun --all --verify thorough
    _mtrCheck 'migrateToRaid rejects unknown verify level' test "$mtrStatus" -eq 2
    _mtrRun --all --yes-delete
    _mtrCheck 'migrateToRaid rejects --yes-delete without --remove-source' test "$mtrStatus" -eq 2
    _mtrRun --status --check
    _mtrCheck 'migrateToRaid rejects two actions' test "$mtrStatus" -eq 2
    _mtrRun --remove-source --all
    _mtrCheck 'remove-source refuses --all' test "$mtrStatus" -eq 2
    _mtrRun
    _mtrCheck 'migration requires a selection' test "$mtrStatus" -eq 2
    _mtrRun --source video1
    assertContains "$mtrOutput" 'mapping video1 is disabled' 'disabled mapping cannot be migrated'
    _mtrRun --source nosuch
    assertContains "$mtrOutput" "no mapping named 'nosuch'" 'unknown mapping is rejected'
}

## configuration

testMigrateToRaidConfigTemplate() {
    _mtrSandbox
    mtrConfig="$projectDir/configs/migrateToRaid/config.json"
    _mtrRun --status
    _mtrCheck 'template configuration parses' test "$mtrStatus" -eq 0
    assertContains "$mtrOutput" 'myPictures' 'template lists the pictures mapping'
    assertContains "$mtrOutput" 'not run*' 'template mappings are disabled'
    _mtrRun --all
    assertContains "$mtrOutput" 'no enabled mappings match' 'template enables nothing by default'
}

testMigrateToRaidConfigInvalid() {
    _mtrSandbox
    printf '{"mappings": "nope"}' >"$mtrConfig"
    _mtrRun --status
    assertContains "$mtrOutput" 'invalid configuration' 'invalid configuration is rejected'
    printf '{"mappings":[{"name":"a","source":"/x","destination":"/y"},{"name":"a","source":"/z","destination":"/y"}]}' >"$mtrConfig"
    _mtrRun --status
    assertContains "$mtrOutput" 'duplicate mapping name' 'duplicate mapping names are rejected'
    _mtrSandbox
    sed -i "s|\"destination\": \"$mtrDest\"|\"destination\": \"<RAID_STORAGE_MOUNT>/movies\"|" "$mtrConfig"
    _mtrRun --source movie1
    assertContains "$mtrOutput" 'destination for movie1 is not configured' 'placeholder destination is refused'
}

## preflight

testMigrateToRaidMissingSource() {
    _mtrSandbox
    rm -rf -- "$mtrSource"
    _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'source does not exist' 'missing source is reported'
    _mtrCheck 'missing source fails' test "$mtrStatus" -eq 1
}

testMigrateToRaidSourceNotMounted() {
    _mtrSandbox
    : >"$mtrBox/mounts.empty"
    printf '%s|fuse.mergerfs|pool|storage\n' "$mtrStorage" >"$mtrBox/mounts"
    _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'no filesystem is mounted at' 'unmounted mount point is refused'
    _mtrCheck 'unmounted source copies nothing' test ! -e "$mtrDest"
    _mtrCheck 'unmounted source records no state' test ! -e "$mtrState/movie1.state"
}

testMigrateToRaidDestinationUnavailable() {
    _mtrSandbox
    FAKE_SSH_FAIL=1 _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'raid-pc is not reachable over SSH' 'unreachable raid-pc is reported'
    _mtrCheck 'unreachable raid-pc fails' test "$mtrStatus" -eq 1
}

testMigrateToRaidDestinationNotMounted() {
    _mtrSandbox
    printf '%s|ntfs3|UUID-MOVIE1|/dev/sdx1\n' "$mtrSource" >"$mtrBox/mounts"
    _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'raid-pc storage is not mounted' 'unmounted raid-pc storage is refused'
    _mtrCheck 'unmounted raid-pc storage receives nothing' test ! -e "$mtrDest"
}

testMigrateToRaidInsufficientSpace() {
    _mtrSandbox
    FAKE_DF_AVAIL=2000 _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'insufficient space on raid-pc' 'insufficient space is reported'
    _mtrCheck 'insufficient space starts no transfer' test ! -e "$mtrDest"
}

## migration

testMigrateToRaidDryRun() {
    _mtrSandbox
    _mtrRun --source movie1
    _mtrCheck 'preview succeeds' test "$mtrStatus" -eq 0
    assertContains "$mtrOutput" "Source:       $mtrSource" 'preview shows source'
    assertContains "$mtrOutput" "Destination:  raid-pc:$mtrDest" 'preview shows destination'
    assertContains "$mtrOutput" 'Reachable:    yes' 'preview shows reachability'
    assertContains "$mtrOutput" 'Available:' 'preview shows available space'
    assertContains "$mtrOutput" 'To copy:      2 files, 2 directories' 'preview counts entries to copy'
    assertContains "$mtrOutput" '--ignore-existing' 'preview shows the rsync command'
    assertContains "$mtrOutput" 'Preview only' 'preview says nothing changed'
    _mtrCheck 'preview copies nothing' test ! -e "$mtrDest"
    _mtrCheck 'preview writes no state' test ! -e "$mtrState/movie1.state"
}

testMigrateToRaidSuccessfulCopy() {
    _mtrSandbox
    _mtrRun --source movie1 --confirm
    _mtrCheck 'confirmed migration succeeds' test "$mtrStatus" -eq 0
    assertContains "$mtrOutput" 'VERIFIED (quick)' 'quick verification is reported'
    _mtrCheck 'destination matches source' _mtrSameTree
    _mtrCheck 'excluded system folder is not copied' test ! -e "$mtrDest/lost+found"
    _mtrCheck 'copy state is complete' test "$(_mtrState copyStatus)" = complete
    _mtrCheck 'verify state is quick verified' test "$(_mtrState verifyStatus)/$(_mtrState verifyLevel)" = verified/quick
    _mtrCheck 'source identity is recorded' test "$(_mtrState sourceUuid)" = UUID-MOVIE1
    _mtrCheck 'source is retained by default' test -f "$mtrSource/Films/A Film (2001)/A Film (2001).mkv"
    _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'To copy:      0 files, 0 directories' 'rerun copies nothing again'
}

testMigrateToRaidInterruptedResume() {
    local film="$mtrSource"
    _mtrSandbox
    film="Films/A Film (2001)/A Film (2001).mkv"
    : >"$mtrBox/interrupt"
    FAKE_RSYNC_INTERRUPT="$mtrBox/interrupt" _mtrRun --source movie1 --confirm
    _mtrCheck 'interrupted transfer fails' test "$mtrStatus" -eq 1
    assertContains "$mtrOutput" 'rsync exit 12' 'interruption reports the rsync status'
    _mtrCheck 'interrupted copy is recorded as partial' test "$(_mtrState copyStatus)" = partial
    _mtrCheck 'interrupted copy is never verified' test "$(_mtrState verifyStatus)" = pending
    _mtrCheck 'partial data is kept in the partial directory' test -s "$mtrDest/Films/A Film (2001)/.rsync-partial/A Film (2001).mkv"
    _mtrCheck 'no incomplete file at the final path' test ! -e "$mtrDest/$film"
    _mtrRun --source movie1
    assertContains "$mtrOutput" 'Conflicts:    0' 'partial file is not a destination conflict'
    _mtrRun --source movie1 --confirm --verify full
    _mtrCheck 'resumed migration succeeds' test "$mtrStatus" -eq 0
    _mtrCheck 'resumed file is complete' cmp -s "$mtrSource/$film" "$mtrDest/$film"
    _mtrCheck 'resumed migration is fully verified' test "$(_mtrState verifyStatus)/$(_mtrState verifyLevel)" = verified/full
}

testMigrateToRaidSourceGrowsDuringCopy() {
    _mtrSandbox
    FAKE_RSYNC_ADD_SOURCE="$mtrSource/late arrival.mkv" _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'Copying (pass 2)' 'final synchronisation pass copies late files'
    _mtrCheck 'late file reaches raid-pc' test -f "$mtrDest/late arrival.mkv"
    _mtrCheck 'grown source still verifies' test "$(_mtrState verifyStatus)" = verified
}

## collisions

testMigrateToRaidIdenticalDestination() {
    local inode
    _mtrSandbox
    mkdir -p "$mtrDest/Films/A Film (2001)"
    cp -p "$mtrSource/Films/A Film (2001)/A Film (2001).mkv" "$mtrDest/Films/A Film (2001)/"
    inode="$(stat -c %i "$mtrDest/Films/A Film (2001)/A Film (2001).mkv")"
    _mtrRun --source movie1
    assertContains "$mtrOutput" 'To copy:      1 files' 'identical destination file is not scheduled'
    _mtrRun --source movie1 --confirm
    _mtrCheck 'identical destination file is left untouched' \
        test "$(stat -c %i "$mtrDest/Films/A Film (2001)/A Film (2001).mkv")" = "$inode"
    _mtrCheck 'identical destination still verifies' test "$(_mtrState verifyStatus)" = verified
}

testMigrateToRaidConflictingDestination() {
    local target
    _mtrSandbox
    target="$mtrDest/Films/A Film (2001)/A Film (2001).mkv"
    mkdir -p "$(dirname "$target")"
    printf 'a different film\n' >"$target"
    _mtrRun --source movie1
    assertContains "$mtrOutput" 'Conflicts:    1' 'preview discovers the conflict'
    _mtrRun --source movie1 --confirm
    _mtrCheck 'conflict fails the migration' test "$mtrStatus" -eq 1
    _mtrCheck 'conflicting destination file is not overwritten' test "$(cat "$target")" = 'a different film'
    _mtrCheck 'non-conflicting files are still copied' test -f "$mtrDest/Films/A Film (2001)/A Film (2001).en.srt"
    _mtrCheck 'conflict state is recorded' test "$(_mtrState copyStatus)/$(_mtrState conflicts)" = conflicts/1
    _mtrCheck 'conflicts are listed for review' grep -q 'A Film (2001).mkv' "$mtrState/movie1.conflicts"
    _mtrCheck 'conflicting migration is not verified' test "$(_mtrState verifyStatus)" != verified
}

## verification

testMigrateToRaidFullVerification() {
    _mtrSandbox
    _mtrRun --source movie1 --confirm --verify full
    _mtrCheck 'full verification succeeds' test "$mtrStatus" -eq 0
    assertContains "$mtrOutput" 'Checksums match for 2 files' 'full verification checksums every file'
    _mtrCheck 'full verification is recorded' test "$(_mtrState verifyLevel)" = full
    _mtrCheck 'verified manifest is stored' test -s "$mtrState/movie1.manifest"
}

testMigrateToRaidFailedVerification() {
    local target
    _mtrSandbox
    _mtrRun --source movie1 --confirm
    target="$mtrDest/Films/A Film (2001)/A Film (2001).en.srt"
    printf 'subtitlez\n' >"$target.new"
    touch -r "$target" "$target.new"
    mv -f "$target.new" "$target"
    _mtrRun --source movie1 --verify-only --verify full
    _mtrCheck 'corrupted destination fails verification' test "$mtrStatus" -eq 1
    assertContains "$mtrOutput" '1 files differ by checksum' 'checksum mismatch is reported'
    _mtrCheck 'failed verification is recorded' test "$(_mtrState verifyStatus)" = failed
}

## check

testMigrateToRaidCheck() {
    _mtrSandbox
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'NOT SAFE TO REMOVE DISK' 'unmigrated disk is not safe'
    _mtrRun --source movie1 --confirm
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'a full checksum verification is required' 'quick verification is never safe'
    _mtrCheck 'quick-verified disk check fails' test "$mtrStatus" -eq 1
    _mtrRun --source movie1 --verify-only --verify full
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'COPY VERIFIED' 'full verification reports copy verified'
    assertContains "$mtrOutput" 'SAFE TO REMOVE DISK' 'verified and protected disk is safe'
    assertContains "$mtrOutput" $'COPY VERIFIED\nSNAPRAID PARITY VERIFIED\nSAFE TO REMOVE DISK' 'raid-pc SAFE names verified parity'
    _mtrCheck 'raid-pc SAFE is not described as single-copy' _mtrNotContains "$mtrOutput" 'AUTHORITATIVE'
    _mtrCheck 'safe disk check succeeds' test "$mtrStatus" -eq 0

    FAKE_PROTECTION_STATUS=2 _mtrRun --check movie1
    assertContains "$mtrOutput" 'COPY VERIFIED' 'copy stays verified without parity'
    assertContains "$mtrOutput" 'SnapRAID parity check failed' 'missing parity is explained'
    assertContains "$mtrOutput" 'NOT SAFE TO REMOVE DISK' 'unprotected raid-pc is not safe'

    sed -i 's|"command": "fake-protection"|"command": "<RAID_PROTECTION_CHECK_COMMAND>"|' "$mtrConfig"
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'parity has not been established' 'unconfigured protection is not safe'
    sed -i 's|"command": "<RAID_PROTECTION_CHECK_COMMAND>"|"command": "fake-protection"|' "$mtrConfig"

    printf 'new\n' >"$mtrSource/new episode.mkv"
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'source has changed since it was verified' 'changed source is not safe'
    rm -f "$mtrSource/new episode.mkv"

    sed -i 's/UUID-MOVIE1/UUID-OTHER/' "$mtrBox/mounts"
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'is not the one migrated' 'different disk at the mount point is not safe'
    _mtrRun --source movie1 --confirm
    assertContains "$mtrOutput" 'is not the one migrated' 'different disk cannot inherit migration state'
    sed -i 's/UUID-OTHER/UUID-MOVIE1/' "$mtrBox/mounts"

    rm -f "$mtrDest/Films/A Film (2001)/A Film (2001).en.srt"
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'destination no longer matches' 'damaged destination is not safe'
}

## removal

testMigrateToRaidRemovalRefused() {
    _mtrSandbox
    _mtrRun --source movie1 --confirm
    _mtrRun --source movie1 --remove-source --confirm --yes-delete
    _mtrCheck 'removal without full verification fails' test "$mtrStatus" -eq 1
    assertContains "$mtrOutput" 'refusing to remove source data' 'removal refusal is explained'
    _mtrCheck 'refused removal keeps source' _mtrSameTree

    _mtrRun --source movie1 --verify-only --verify full
    FAKE_PROTECTION_STATUS=2 _mtrRun --source movie1 --remove-source --confirm --yes-delete
    _mtrCheck 'removal without parity protection fails' test "$mtrStatus" -eq 1
    _mtrCheck 'unprotected removal keeps source' _mtrSameTree

    _mtrRun --source movie1 --remove-source --confirm
    assertContains "$mtrOutput" 'needs interactive confirmation' 'non-interactive removal needs --yes-delete'
    _mtrCheck 'unconfirmed removal keeps source' _mtrSameTree
}

testMigrateToRaidRemovalAllowed() {
    _mtrSandbox
    _mtrRun --source movie1 --confirm --verify full
    _mtrRun --source movie1 --remove-source
    assertContains "$mtrOutput" 'Delete 2 verified files and links' 'removal preview shows the plan'
    _mtrCheck 'removal preview deletes nothing' _mtrSameTree
    _mtrRun --source movie1 --remove-source --confirm --yes-delete
    _mtrCheck 'verified removal succeeds' test "$mtrStatus" -eq 0
    _mtrCheck 'migrated files are removed' test ! -e "$mtrSource/Films"
    _mtrCheck 'mount point is kept' test -d "$mtrSource"
    _mtrCheck 'excluded system folder is kept' test -f "$mtrSource/lost+found/#123"
    _mtrCheck 'destination is untouched by removal' test -f "$mtrDest/Films/A Film (2001)/A Film (2001).mkv"
    _mtrCheck 'removal is recorded' test "$(_mtrState sourceRemoved)" = yes
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'SAFE TO REMOVE DISK' 'emptied disk remains safe'
    printf 'new\n' >"$mtrSource/written later.mkv"
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'source contains data that was not verified' 'new data after removal is not safe'
}

## status

testMigrateToRaidStatus() {
    _mtrSandbox
    _mtrRun --status
    assertContains "$mtrOutput" 'not run' 'status shows unmigrated mapping'
    _mtrRun --source movie1 --confirm --verify full
    _mtrRun --status
    assertContains "$mtrOutput" 'verified(full)' 'status shows verification level'
    assertContains "$mtrOutput" 'retained' 'status shows source retained'
    assertContains "$mtrOutput" 'Migrated:' 'status shows migrated total'
    assertContains "$mtrOutput" 'Remaining:' 'status shows remaining total'
}

## filenames

testMigrateToRaidSpecialFilenames() {
    local names=(
        "Tom & Jerry (1940) [Remastered].mkv"
        "Ocean's Eleven (2001).mkv"
        "-leading dash.mkv"
        "semi;colon \$dollar \`tick\` #hash !bang.mkv"
        "Amélie – Le Fabuleux Destin.mkv"
        "*star? and back\\slash.mkv"
        $'tab\there.mkv'
        $'line\nbreak.mkv'
    )
    local name dir="$mtrSource"
    _mtrSandbox
    dir="$mtrSource/Shows/Spaced Out (1999) & Friends'"
    mkdir -p "$dir"
    for name in "${names[@]}"; do
        printf '%s\n' "$name" >"$dir/$name"
    done
    _mtrRun --source movie1 --confirm --verify full
    _mtrCheck 'special filenames migrate and verify' test "$mtrStatus" -eq 0
    _mtrCheck 'special filenames arrive intact' _mtrSameTree
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'SAFE TO REMOVE DISK' 'special filenames can be checked'
    _mtrRun --source movie1 --remove-source --confirm --yes-delete
    _mtrCheck 'special filenames are removed after verification' test ! -e "$mtrSource/Shows"
}

## shared destinations

# movie1 and movie2 both migrate into one Movies folder on raid-pc.
testMigrateToRaidSharedDestination() {
    local movie2
    _mtrSandbox
    movie2="$mtrBox/mnt/movie2"
    mtrDest="$mtrStorage/Movies"
    mkdir -p "$movie2/Films/A Film (2001)" "$movie2/Films/B Film (2002)"
    printf 'second disk film\n' >"$movie2/Films/B Film (2002)/B Film (2002).mkv"
    cp -p "$mtrSource/Films/A Film (2001)/A Film (2001).en.srt" "$movie2/Films/A Film (2001)/"
    printf 'different cut\n' >"$movie2/Films/A Film (2001)/A Film (2001).mkv"
    printf '%s|ntfs3|UUID-MOVIE2|/dev/sdy1\n' "$movie2" >>"$mtrBox/mounts"
    jq --arg dest "$mtrDest" --arg src2 "$movie2" '
        .mappings[0].destination = $dest
        | .mappings += [{name: "movie2", label: "Movies 2", type: "movies", source: $src2, destination: $dest, enabled: true}]
    ' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"

    _mtrRun --source movie1 --confirm
    _mtrCheck 'first disk migrates into the shared folder' test "$(_mtrState verifyStatus)" = verified
    _mtrRun --type movies --confirm
    assertContains "$mtrOutput" 'Conflicts:    1' 'same title with different content across disks is a conflict'
    _mtrCheck 'shared-folder conflict is not overwritten' cmp -s "$mtrSource/Films/A Film (2001)/A Film (2001).mkv" "$mtrDest/Films/A Film (2001)/A Film (2001).mkv"
    _mtrCheck 'second disk adds its other titles' test -f "$mtrDest/Films/B Film (2002)/B Film (2002).mkv"
    _mtrCheck 'second disk conflict is recorded' test "$(sed -n 's/^copyStatus=//p' "$mtrState/movie2.state")" = conflicts
    _mtrCheck 'first disk stays verified despite shared folder' test "$(_mtrState verifyStatus)" = verified

    rm -f "$movie2/Films/A Film (2001)/A Film (2001).mkv"
    _mtrRun --source movie2 --confirm --verify full
    _mtrCheck 'resolved second disk verifies' test "$mtrStatus" -eq 0
    _mtrRun --source movie1 --verify-only --verify full
    _mtrRun --check movie1
    assertContains "$mtrOutput" 'SAFE TO REMOVE DISK' 'other disk content in the shared folder does not affect the check'
}

## folder sources

# /mnt/myVideo/TV merges into TV while the rest of /mnt/myVideo goes to Video.
testMigrateToRaidFolderSource() {
    local myVideo
    _mtrSandbox
    myVideo="$mtrBox/mnt/myVideo"
    mkdir -p "$myVideo/TV/A Show/Season 01" "$myVideo/Home Movies"
    printf 'episode\n' >"$myVideo/TV/A Show/Season 01/A Show S01E01.mkv"
    printf 'holiday\n' >"$myVideo/Home Movies/Holiday 2010.mp4"
    printf '%s|ntfs3|UUID-MYVIDEO|/dev/sdz1\n' "$myVideo" >>"$mtrBox/mounts"
    jq --arg mv "$myVideo" --arg st "$mtrStorage" '
        .mappings = [{name: "myVideoTV", label: "My Video TV", type: "tv", source: ($mv + "/TV"),
                      mountPoint: $mv, destination: ($st + "/TV"), enabled: true}]
    ' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"

    _mtrRun --source myVideoTV --confirm --verify full
    _mtrCheck 'folder source migrates' test -f "$mtrStorage/TV/A Show/Season 01/A Show S01E01.mkv"
    _mtrCheck 'folder source does not copy the rest of the disk' test ! -e "$mtrStorage/TV/Home Movies"
    _mtrRun --check myVideoTV
    assertContains "$mtrOutput" 'SAFE TO REMOVE SOURCE FOLDER' 'verified folder is safe to remove'
    assertContains "$mtrOutput" 'Home Movies is not covered by any mapping' 'uncovered disk content is reported'
    _mtrCheck 'disk with uncovered content is not safe' test "$mtrStatus" -eq 1

    jq --arg mv "$myVideo" --arg st "$mtrStorage" '
        .mappings += [{name: "myVideo", label: "My Video", type: "video", source: $mv,
                       destination: ($st + "/Video"), enabled: true}]
    ' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --status
    assertContains "$mtrOutput" 'add "TV" to the excludes of myVideo' 'overlapping mappings are rejected'

    jq '.mappings[1].excludes = ["TV"]' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --check myVideoTV
    assertContains "$mtrOutput" 'mapping myVideo is not safe to remove' 'disk waits for its other mappings'
    _mtrRun --source myVideo --confirm --verify full
    _mtrCheck 'excluded folder is not copied by the outer mapping' test ! -e "$mtrStorage/Video/TV"
    _mtrCheck 'outer mapping copies the rest of the disk' test -f "$mtrStorage/Video/Home Movies/Holiday 2010.mp4"
    _mtrRun --check myVideoTV
    assertContains "$mtrOutput" "Disk $myVideo (mappings: myVideoTV myVideo)"$'\n''SAFE TO REMOVE DISK' 'fully covered disk is safe'
    assertContains "$mtrOutput" '  - myVideo: SNAPRAID PARITY VERIFIED' 'disk verdict lists the basis of each mapping'
    _mtrCheck 'fully covered disk check succeeds' test "$mtrStatus" -eq 0
}

## local destinations

# Adds a mounted /mnt/media-style local destination and a myPictures disk to
# the sandbox. The myPictures mapping keeps everything except Movies locally.
_mtrLocalSandbox() {
    _mtrSandbox
    mtrMedia="$mtrBox/mnt/media"
    mtrPictures="$mtrBox/mnt/myPictures"
    mkdir -p "$mtrMedia" "$mtrPictures/Family/2010" "$mtrPictures/Movies/C Film (2003)"
    printf 'birthday\n' >"$mtrPictures/Family/2010/Birthday 001.jpg"
    printf 'third film\n' >"$mtrPictures/Movies/C Film (2003)/C Film (2003).mkv"
    printf '%s|ext4|UUID-MEDIA|/dev/sdm1\n%s|ntfs3|UUID-MYPICTURES|/dev/sdp1\n' "$mtrMedia" "$mtrPictures" >>"$mtrBox/mounts"
    jq --arg media "$mtrMedia" --arg pic "$mtrPictures" '
        .localDestination = {mount: $media, fsType: "ext4", uuid: "UUID-MEDIA",
                             protection: {name: "local media protection", command: "<MEDIA_PROTECTION_CHECK_COMMAND>"}}
        | .mappings = [{name: "myPictures", label: "Pictures", type: "pictures", source: $pic, excludes: ["Movies"],
                        target: "local", destination: ($media + "/Pictures"), enabled: true}]
    ' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
}

_mtrLocalState() {
    sed -n "s/^$2=//p" "$mtrState/$1.state" 2>/dev/null
}

testMigrateToRaidLocalDestination() {
    _mtrLocalSandbox
    FAKE_SSH_FAIL=1 _mtrRun --source myPictures
    _mtrCheck 'local preview succeeds without raid-pc' test "$mtrStatus" -eq 0
    assertContains "$mtrOutput" "Destination:  $mtrMedia/Pictures (local)" 'local preview shows the local destination'
    assertContains "$mtrOutput" "Mounted:      $mtrMedia (ext4 UUID UUID-MEDIA)" 'local preview shows the verified mount'
    _mtrCheck 'local preview copies nothing' test ! -e "$mtrMedia/Pictures"

    FAKE_SSH_FAIL=1 _mtrRun --source myPictures --confirm --verify full
    _mtrCheck 'local migration succeeds without SSH' test "$mtrStatus" -eq 0
    _mtrCheck 'local migration copies retained content' cmp -s "$mtrPictures/Family/2010/Birthday 001.jpg" "$mtrMedia/Pictures/Family/2010/Birthday 001.jpg"
    _mtrCheck 'local migration does not copy the excluded folder' test ! -e "$mtrMedia/Pictures/Movies"
    _mtrCheck 'local migration is fully verified' test "$(_mtrLocalState myPictures verifyStatus)/$(_mtrLocalState myPictures verifyLevel)" = verified/full
    _mtrCheck 'local destination kind is recorded' test "$(_mtrLocalState myPictures destinationKind)" = local

    FAKE_SSH_FAIL=1 _mtrRun --check myPictures
    assertContains "$mtrOutput" 'COPY VERIFIED' 'local copy can be verified'
    assertContains "$mtrOutput" 'localDestination.protection.command' 'unconfigured local protection is explained'
    assertContains "$mtrOutput" 'NOT SAFE TO REMOVE SOURCE FOLDER' 'unconfigured local protection is not safe'

    jq '.localDestination.protection.command = "fake-protection"' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    FAKE_PROTECTION_STATUS=3 FAKE_SSH_FAIL=1 _mtrRun --check myPictures
    assertContains "$mtrOutput" 'local media protection check failed (exit 3)' 'failing local protection is not safe'
    FAKE_SSH_FAIL=1 _mtrRun --check myPictures
    assertContains "$mtrOutput" $'LOCAL MEDIA PROTECTION VERIFIED\nSAFE TO REMOVE SOURCE FOLDER' 'local protection command runs locally'

    jq '.localDestination.protection = {required: false}' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    FAKE_SSH_FAIL=1 _mtrRun --check myPictures
    assertContains "$mtrOutput" 'single-copy local storage is accepted for' 'accepted single-copy local destination is reported'
    assertContains "$mtrOutput" $'COPY VERIFIED\nDESTINATION ACCEPTED AS AUTHORITATIVE (single copy, not redundant)\nSAFE TO REMOVE SOURCE FOLDER' 'single-copy SAFE names the accepted authoritative destination'
    _mtrCheck 'single-copy SAFE does not claim protection' _mtrNotContains "$mtrOutput" 'PARITY VERIFIED'
    assertContains "$mtrOutput" 'Movies is not covered by any mapping' 'disk waits for the folder migrated elsewhere'
    _mtrRun --status
    assertContains "$mtrOutput" 'safe(1 copy)' 'status distinguishes single-copy SAFE'

    rm -f "$mtrMedia/Pictures/Family/2010/Birthday 001.jpg"
    FAKE_SSH_FAIL=1 _mtrRun --check myPictures
    assertContains "$mtrOutput" 'destination no longer matches' 'damaged local destination is not safe'
}

testMigrateToRaidLocalDestinationRefused() {
    _mtrLocalSandbox
    sed -i "\\|^$mtrMedia|d" "$mtrBox/mounts"
    _mtrRun --source myPictures --confirm
    assertContains "$mtrOutput" "no filesystem is mounted at $mtrMedia" 'unmounted local destination is refused'
    _mtrCheck 'unmounted local destination receives nothing' test ! -e "$mtrMedia/Pictures"
    _mtrCheck 'unmounted local destination records no state' test ! -e "$mtrState/myPictures.state"

    _mtrLocalSandbox
    sed -i 's/UUID-MEDIA|/UUID-OTHERDISK|/' "$mtrBox/mounts"
    _mtrRun --source myPictures --confirm
    assertContains "$mtrOutput" 'has UUID UUID-OTHERDISK, configuration expects UUID-MEDIA' 'different local disk is refused'
    _mtrCheck 'different local disk receives nothing' test ! -e "$mtrMedia/Pictures"

    _mtrLocalSandbox
    sed -i "s/|ext4|UUID-MEDIA|/|ntfs3|UUID-MEDIA|/" "$mtrBox/mounts"
    _mtrRun --source myPictures --confirm
    assertContains "$mtrOutput" 'is ntfs3, expected ext4' 'unexpected local filesystem type is refused'

    _mtrLocalSandbox
    jq '.localDestination.uuid = "<MEDIA_FS_UUID>"' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --source myPictures
    assertContains "$mtrOutput" 'localDestination.uuid is not configured' 'placeholder local UUID is refused'

    _mtrLocalSandbox
    jq '.localDestination.uuid = "UUID-MYPICTURES"' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    sed -i 's/UUID-MEDIA|/UUID-MYPICTURES|/' "$mtrBox/mounts"
    _mtrRun --source myPictures --confirm
    assertContains "$mtrOutput" 'is the source filesystem' 'local destination on the source filesystem is refused'

    _mtrLocalSandbox
    jq --arg dest "$mtrMedia/Pictures" '.mappings[0].source = $dest | .mappings[0].mountPoint = $dest' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --source myPictures
    assertContains "$mtrOutput" 'overlaps its source' 'local destination inside its source is refused'

    _mtrLocalSandbox
    jq '.mappings[0].target = "elsewhere"' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --status
    assertContains "$mtrOutput" 'target must be remote (raid-pc) or local' 'unknown target is rejected'
}

# /mnt/myVideo: TV goes to raid-pc, the rest stays local, encrypted is
# handled elsewhere and keeps the disk from being safe to remove.
testMigrateToRaidMixedDestinations() {
    local myVideo
    _mtrLocalSandbox
    myVideo="$mtrBox/mnt/myVideo"
    mkdir -p "$myVideo/TV/A Show" "$myVideo/Home Movies" "$myVideo/encrypted"
    printf 'episode\n' >"$myVideo/TV/A Show/A Show S01E01.mkv"
    printf 'holiday\n' >"$myVideo/Home Movies/Holiday 2010.mp4"
    printf 'secret\n' >"$myVideo/encrypted/vault.bin"
    printf '%s|ntfs3|UUID-MYVIDEO|/dev/sdz1\n' "$myVideo" >>"$mtrBox/mounts"
    jq --arg mv "$myVideo" --arg st "$mtrStorage" --arg media "$mtrMedia" '
        .localDestination.protection = {required: false}
        | .mappings = [
            {name: "myVideo", label: "My Video", type: "video", source: $mv, excludes: ["TV", "encrypted"],
             target: "local", destination: ($media + "/Video"), enabled: true},
            {name: "myVideoTV", label: "My Video TV", type: "tv", source: ($mv + "/TV"), mountPoint: $mv,
             destination: ($st + "/TV"), enabled: true}]
    ' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"

    _mtrRun --all --confirm --verify full
    _mtrCheck 'mixed destinations migrate' test "$mtrStatus" -eq 0
    _mtrCheck 'retained video goes to the local destination' test -f "$mtrMedia/Video/Home Movies/Holiday 2010.mp4"
    _mtrCheck 'TV goes to raid-pc' test -f "$mtrStorage/TV/A Show/A Show S01E01.mkv"
    _mtrCheck 'TV is not kept locally' test ! -e "$mtrMedia/Video/TV"
    _mtrCheck 'encrypted is not copied locally' test ! -e "$mtrMedia/Video/encrypted"
    _mtrCheck 'encrypted is not copied to raid-pc' test -z "$(find "$mtrStorage" -name encrypted)"

    FAKE_PROTECTION_STATUS=2 _mtrRun --check myVideo
    assertContains "$mtrOutput" 'SnapRAID parity check failed' 'raid-pc mapping on the disk still needs parity'
    assertContains "$mtrOutput" 'mapping myVideoTV is not safe to remove' 'disk waits for the raid-pc mapping'

    _mtrRun --check myVideo
    assertContains "$mtrOutput" 'SAFE TO REMOVE SOURCE FOLDER' 'each mapping is judged against its own destination'
    assertContains "$mtrOutput" 'encrypted is not covered by any mapping' 'excluded encrypted folder keeps the disk'
    assertContains "$mtrOutput" "Disk $myVideo (mappings: myVideo myVideoTV)"$'\n''NOT SAFE TO REMOVE DISK' 'disk with encrypted content is not safe'

    _mtrRun --status
    assertContains "$mtrOutput" 'Local protection: ok' 'status shows local protection'
}

testMigrateToRaidTemplateMappings() {
    local template="$projectDir/configs/migrateToRaid/config.json"
    _mtrCheck 'template keeps myPictures remainder local' test "$(jq -r '.mappings[] | select(.name == "myPictures") | [.target, .destination, (.excludes | join(","))] | join(" ")' "$template")" = 'local /mnt/media/Pictures Movies'
    _mtrCheck 'template sends myPictures Movies to raid-pc' test "$(jq -r '.mappings[] | select(.source == "/mnt/myPictures/Movies") | [(.target // "remote"), .destination] | join(" ")' "$template")" = 'remote <RAID_STORAGE_MOUNT>/Movies'
    _mtrCheck 'template keeps myVideo remainder local without TV or encrypted' test "$(jq -r '.mappings[] | select(.name == "myVideo") | [.target, .destination, (.excludes | join(","))] | join(" ")' "$template")" = 'local /mnt/media/Video TV,encrypted'
    _mtrCheck 'template sends myVideo TV to raid-pc' test "$(jq -r '.mappings[] | select(.source == "/mnt/myVideo/TV") | [(.target // "remote"), .destination] | join(" ")' "$template")" = 'remote <RAID_STORAGE_MOUNT>/TV'
    _mtrCheck 'template has no permanent /mnt/video1 source' test -z "$(jq -r '.mappings[] | select(.source == "/mnt/video1" or .destination == "/mnt/video1")' "$template")"
    _mtrCheck 'andy-pc template leaves the old video1 disk to raid-pc' test -z "$(jq -r '.mappings[] | select(.name == "video1" or (.source | startswith("/mnt/oldVideo1")))' "$template")"
    _mtrCheck 'template local destination is /mnt/media identified by UUID' test "$(jq -r '.localDestination | [.mount, .uuid] | join(" ")' "$template")" = '/mnt/media <MEDIA_FS_UUID>'
    _mtrCheck 'template accepts /mnt/media as single-copy storage' test "$(jq -r '.localDestination.protection.required' "$template")" = false

    template="$projectDir/configs/migrateToRaid/raidPcConfig.json"
    _mtrCheck 'raid-pc template copies the old video1 TV folder into the pool' test "$(jq -r '.mappings[] | select(.name == "video1") | [.source, .mountPoint, .target, .destination, .enabled] | join(" ")' "$template")" = '/mnt/oldVideo1/TV /mnt/oldVideo1 local /mnt/storage/TV false'
    _mtrCheck 'raid-pc template identifies the pool by mount source' test "$(jq -r '.localDestination | [.mount, .fsType, .source, (.uuid // "-")] | join(" ")' "$template")" = '/mnt/storage fuse.mergerfs <STORAGE_MOUNT_SOURCE> -'
    _mtrCheck 'raid-pc template requires SnapRAID protection' test "$(jq -r '.localDestination.protection | [.name, .command, (.required // "-")] | join(" ")' "$template")" = 'SnapRAID parity <RAID_PROTECTION_CHECK_COMMAND> -'
}

## run on raid-pc

# Run on raid-pc: an old disk attached by USB is copied into the local
# mergerFS pool, which has no filesystem UUID and is identified by its mount
# source. SAFE needs SnapRAID protection, run locally.
_mtrPoolSandbox() {
    _mtrSandbox
    mtrOld="$mtrBox/mnt/oldVideo1"
    mtrPool="$mtrBox/mnt/storage"
    mkdir -p "$mtrOld/TV/A Show/Season 01" "$mtrOld/.Trash-1000/files" "$mtrPool"
    printf 'episode\n' >"$mtrOld/TV/A Show/Season 01/A Show S01E01.mkv"
    printf 'deleted\n' >"$mtrOld/.Trash-1000/files/old.mkv"
    printf '%s|fuseblk|UUID-OLDVIDEO1|/dev/sdg1\n%s|fuse.mergerfs||data01:data02\n' "$mtrOld" "$mtrPool" >"$mtrBox/mounts"
    jq --arg old "$mtrOld" --arg pool "$mtrPool" '
        del(.destinationMount)
        | .localDestination = {mount: $pool, fsType: "fuse.mergerfs", source: "data01:data02",
                               protection: {name: "SnapRAID parity", command: "fake-protection"}}
        | .mappings = [{name: "video1", label: "Old video1 disk", type: "tv", source: ($old + "/TV"), mountPoint: $old,
                        uuid: "UUID-OLDVIDEO1", target: "local", destination: ($pool + "/TV"), enabled: true}]
    ' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
}

testMigrateToRaidPoolDestination() {
    _mtrPoolSandbox
    FAKE_SSH_FAIL=1 _mtrRun --source video1
    _mtrCheck 'pool preview succeeds without SSH' test "$mtrStatus" -eq 0
    assertContains "$mtrOutput" "Mounted:      $mtrPool (fuse.mergerfs from data01:data02)" 'pool preview shows the identified pool'

    FAKE_SSH_FAIL=1 _mtrRun --source video1 --confirm --verify full
    _mtrCheck 'old disk migrates into the pool' test "$mtrStatus" -eq 0
    _mtrCheck 'TV folder lands in the pool TV folder' cmp -s "$mtrOld/TV/A Show/Season 01/A Show S01E01.mkv" "$mtrPool/TV/A Show/Season 01/A Show S01E01.mkv"
    _mtrCheck 'TV folder is not nested' test ! -e "$mtrPool/TV/TV"

    FAKE_SSH_FAIL=1 _mtrRun --check video1
    assertContains "$mtrOutput" $'COPY VERIFIED\nSNAPRAID PARITY VERIFIED\nSAFE TO REMOVE SOURCE FOLDER' 'pool SAFE names SnapRAID parity'
    assertContains "$mtrOutput" '.Trash-1000 is not covered by any mapping' 'uncovered trash keeps the old disk'
    FAKE_PROTECTION_STATUS=2 FAKE_SSH_FAIL=1 _mtrRun --check video1
    assertContains "$mtrOutput" 'NOT SAFE TO REMOVE SOURCE FOLDER' 'pool without parity is not safe'
}

testMigrateToRaidPoolDestinationRefused() {
    _mtrPoolSandbox
    sed -i 's/|data01:data02$/|data01/' "$mtrBox/mounts"
    _mtrRun --source video1 --confirm
    assertContains "$mtrOutput" 'is mounted from data01, configuration expects data01:data02' 'different pool is refused'
    _mtrCheck 'different pool receives nothing' test ! -e "$mtrPool/TV"

    _mtrPoolSandbox
    sed -i "\\|^$mtrPool|d" "$mtrBox/mounts"
    _mtrRun --source video1 --confirm
    assertContains "$mtrOutput" "no filesystem is mounted at $mtrPool" 'unmounted pool is refused'
    _mtrCheck 'unmounted pool receives nothing' test ! -e "$mtrPool/TV"

    _mtrPoolSandbox
    jq '.localDestination.source = "<STORAGE_MOUNT_SOURCE>"' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --source video1
    assertContains "$mtrOutput" 'localDestination.source is not configured' 'placeholder pool source is refused'

    _mtrPoolSandbox
    jq 'del(.localDestination.source)' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    _mtrRun --source video1
    assertContains "$mtrOutput" 'localDestination.uuid (or .source' 'unidentified local destination is refused'

    _mtrPoolSandbox
    jq '.localDestination.source = "/dev/sdg1"' "$mtrConfig" >"$mtrConfig.new" && mv "$mtrConfig.new" "$mtrConfig"
    sed -i 's/|data01:data02$/|\/dev\/sdg1/' "$mtrBox/mounts"
    _mtrRun --source video1 --confirm
    assertContains "$mtrOutput" 'is the source filesystem (/dev/sdg1)' 'pool on the source device is refused'

    _mtrPoolSandbox
    mtrConfig="$projectDir/configs/migrateToRaid/raidPcConfig.json"
    _mtrRun --status
    _mtrCheck 'raid-pc template parses' test "$mtrStatus" -eq 0
    _mtrRun --all
    assertContains "$mtrOutput" 'no enabled mappings match' 'raid-pc template enables nothing by default'
}

migrateToRaidTestsRun() {
    testMigrateToRaidHelp
    testMigrateToRaidArgumentErrors
    testMigrateToRaidConfigTemplate
    testMigrateToRaidConfigInvalid
    testMigrateToRaidMissingSource
    testMigrateToRaidSourceNotMounted
    testMigrateToRaidDestinationUnavailable
    testMigrateToRaidDestinationNotMounted
    testMigrateToRaidInsufficientSpace
    testMigrateToRaidDryRun
    testMigrateToRaidSuccessfulCopy
    testMigrateToRaidInterruptedResume
    testMigrateToRaidSourceGrowsDuringCopy
    testMigrateToRaidIdenticalDestination
    testMigrateToRaidConflictingDestination
    testMigrateToRaidFullVerification
    testMigrateToRaidFailedVerification
    testMigrateToRaidCheck
    testMigrateToRaidRemovalRefused
    testMigrateToRaidRemovalAllowed
    testMigrateToRaidStatus
    testMigrateToRaidSpecialFilenames
    testMigrateToRaidSharedDestination
    testMigrateToRaidFolderSource
    testMigrateToRaidLocalDestination
    testMigrateToRaidLocalDestinationRefused
    testMigrateToRaidMixedDestinations
    testMigrateToRaidTemplateMappings
    testMigrateToRaidPoolDestination
    testMigrateToRaidPoolDestinationRefused
}

# Standalone run: provide the small harness that runTests.sh normally supplies.
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    set -Eeuo pipefail
    projectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    testStateDir="$(mktemp -d "${TMPDIR:-/tmp}/migrateToRaid-tests.XXXXXX")"
    trap 'rm -rf -- "$testStateDir"' EXIT
    passed=0
    failed=0
    assertContains() {
        if [[ "$1" == *"$2"* ]]; then
            printf 'PASS  %s\n' "$3"
            ((passed += 1))
        else
            printf 'FAIL  %s\nExpected: %s\nOutput:\n%s\n' "$3" "$2" "$1"
            ((failed += 1))
        fi
    }
    migrateToRaidTestsRun
    printf '\n%d passed, %d failed\n' "$passed" "$failed"
    ((failed == 0))
fi
