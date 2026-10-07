#!/usr/bin/env bash
# Tests for pullTvPcVideos.sh. Sourced from runTests.sh.

_pullScript() {
    printf '%s' "$projectDir/pullTvPcVideos.sh"
}

_pullLogUtilsStub() {
    local stub="$testStateDir/logUtils.sh"
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
log_box() { echo "=== $1 ==="; }
EOF
    fi
    printf '%s' "$stub"
}

_pullFakeBin() {
    local fakeBin="$testStateDir/pull-fake-bin"
    mkdir -p "$fakeBin"
    cat >"$fakeBin/ssh" <<'EOF'
#!/usr/bin/env bash
if [[ -n "${PULL_SSH_RECORD:-}" ]]; then
    printf '%s\n' "$*" >>"$PULL_SSH_RECORD"
fi
echo /home/andy/Downloads
exit 0
EOF
    cat >"$fakeBin/rsync" <<'EOF'
#!/usr/bin/env bash
if [[ -n "${PULL_RSYNC_RECORD:-}" ]]; then
    printf '%s\n' "$@" >"$PULL_RSYNC_RECORD"
fi
exit 0
EOF
    chmod +x "$fakeBin/ssh" "$fakeBin/rsync"
    printf '%s' "$fakeBin"
}

_pullRun() {
    local destDir
    destDir="$(mktemp -d "$testStateDir/pull-dest.XXXXXX")"
    PULL_RSYNC_RECORD="$testStateDir/rsync.args"
    PULL_SSH_RECORD="$testStateDir/ssh.args"
    : >"$PULL_RSYNC_RECORD"
    : >"$PULL_SSH_RECORD"
    export PULL_RSYNC_RECORD PULL_SSH_RECORD
    PATH="$(_pullFakeBin):$PATH" LOG_UTILS="$(_pullLogUtilsStub)" \
        "$(_pullScript)" --dest "$destDir" "$@"
}

testPullTvPcVideosHelp() {
    local output
    output="$("$(_pullScript)" --help)"
    assertContains "$output" '--confirm' 'help documents --confirm'
    assertContains "$output" '--ext EXT' 'help documents --ext for other file types'
    assertContains "$output" '--all' 'help documents --all for every complete file'
    assertContains "$output" 'Preview only unless --confirm' 'help says preview is the default'
    if [[ "$output" == *'--dry-run'* ]]; then
        printf 'FAIL  help must not expose --dry-run\nOutput:\n%s\n' "$output"
        ((failed += 1))
    else
        printf 'PASS  help does not expose --dry-run\n'
        ((passed += 1))
    fi
}

testPullTvPcVideosRejectsDryRunFlag() {
    local output status=0
    output="$("$(_pullScript)" --dry-run 2>&1)" || status=$?
    if ((status == 2)) && [[ "$output" == *'unknown argument: --dry-run'* ]]; then
        printf 'PASS  --dry-run is rejected\n'
        ((passed += 1))
    else
        printf 'FAIL  --dry-run should be rejected\nStatus: %s\nOutput:\n%s\n' "$status" "$output"
        ((failed += 1))
    fi
}

testPullTvPcVideosMissingDest() {
    local output status=0
    output="$(LOG_UTILS="$(_pullLogUtilsStub)" "$(_pullScript)" --dest /tmp/pullTvPcVideos-missing-$$ 2>&1)" || status=$?
    if ((status == 1)) && [[ "$output" == *'destination does not exist'* ]]; then
        printf 'PASS  missing destination fails\n'
        ((passed += 1))
    else
        printf 'FAIL  missing destination should fail\nStatus: %s\nOutput:\n%s\n' "$status" "$output"
        ((failed += 1))
    fi
}

testPullTvPcVideosDryRunDefault() {
    local output
    output="$(_pullRun)"
    assertContains "$output" 'Mode ........... dry-run' 'default mode is dry-run'
    assertContains "$(<"$testStateDir/rsync.args")" '--dry-run' 'default rsync is a preview'
    if [[ "$(<"$testStateDir/rsync.args")" == *'--remove-source-files'* ]]; then
        printf 'FAIL  default rsync must not remove source files\nArgs: %s\n' "$(<"$testStateDir/rsync.args")"
        ((failed += 1))
    else
        printf 'PASS  default rsync does not remove source files\n'
        ((passed += 1))
    fi
}

testPullTvPcVideosExtReplacesDefaults() {
    local args
    _pullRun --ext pdf --ext docx >/dev/null
    args="$(<"$testStateDir/rsync.args")"
    assertContains "$args" '--include=*.pdf' 'ext filter includes pdf'
    assertContains "$args" '--include=*.docx' 'ext filter includes docx'
    if [[ "$args" == *'--include=*.mkv'* ]]; then
        printf 'FAIL  --ext should replace video defaults\nArgs: %s\n' "$args"
        ((failed += 1))
    else
        printf 'PASS  --ext replaces video defaults\n'
        ((passed += 1))
    fi
}

testPullTvPcVideosAllCopiesCompleteFiles() {
    local args
    _pullRun --all >/dev/null
    args="$(<"$testStateDir/rsync.args")"
    assertContains "$args" '--exclude=*.part' 'all mode still skips incomplete downloads'
    if grep -Fxq -- '--exclude=*' "$testStateDir/rsync.args"; then
        printf 'FAIL  --all must not exclude unmatched files\nArgs: %s\n' "$args"
        ((failed += 1))
    else
        printf 'PASS  --all copies complete files of any type\n'
        ((passed += 1))
    fi
}

testPullRemoteRequiresExtOrAll() {
    local output status=0 destDir
    destDir="$(mktemp -d "$testStateDir/pull-dest.XXXXXX")"
    output="$(
        PATH="$(_pullFakeBin):$PATH" LOG_UTILS="$(_pullLogUtilsStub)" \
            "$projectDir/pullRemote.sh" --host tv-pc --dest "$destDir" 2>&1
    )" || status=$?
    if ((status == 2)) && [[ "$output" == *'specify --ext or --all'* ]]; then
        printf 'PASS  generic pull requires --ext or --all\n'
        ((passed += 1))
    else
        printf 'FAIL  generic pull should require --ext or --all\nStatus: %s\nOutput:\n%s\n' "$status" "$output"
        ((failed += 1))
    fi
}

testPullTvPcVideosConfirmRemovesSource() {
    local output
    output="$(_pullRun --confirm)"
    assertContains "$output" 'Mode ........... apply' 'confirm mode is apply'
    assertContains "$(<"$testStateDir/rsync.args")" '--remove-source-files' 'confirm rsync removes source files'
    if [[ "$(<"$testStateDir/rsync.args")" == *'--dry-run'* ]]; then
        printf 'FAIL  confirm rsync must not pass --dry-run\nArgs: %s\n' "$(<"$testStateDir/rsync.args")"
        ((failed += 1))
    else
        printf 'PASS  confirm rsync is a live transfer\n'
        ((passed += 1))
    fi
}
