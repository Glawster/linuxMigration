#!/usr/bin/env bash
set -Eeuo pipefail

projectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
passed=0
failed=0

assertContains() {
    local output="$1" expected="$2" description="$3"
    if [[ "$output" == *"$expected"* ]]; then
        printf 'PASS  %s\n' "$description"
        ((passed += 1))
    else
        printf 'FAIL  %s\nExpected: %s\nOutput:\n%s\n' "$description" "$expected" "$output"
        ((failed += 1))
    fi
}

testBundleHelp() {
    local output
    output="$($projectDir/bootstrap.sh --help)"
    assertContains "$output" 'bundle' 'help documents bundle command'
    assertContains "$output" '--target-release VERSION' 'help documents bundle target release'
}

testBundleRequiresProfile() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" bundle --output /tmp/test-bundle 2>&1)" || status=$?
    [[ "$status" -ne 0 ]] && assertContains "$output" 'bundle requires exactly one --profile NAME' 'bundle requires one profile'
}

testBundleRequiresOutput() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" bundle --profile raid-pc 2>&1)" || status=$?
    [[ "$status" -ne 0 ]] && assertContains "$output" 'bundle requires --output PATH' 'bundle requires output path'
}

testRaidPcBundlePlan() {
    local output target="$TMPDIR/raid-pc-bundle-test"
    rm -rf -- "$target"
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" bundle \
        --profile raid-pc \
        --output "$target" \
        --target-distribution pop \
        --target-release 24.04 \
        --target-architecture amd64)"
    assertContains "$output" 'Profiles ........ raid-server,raid-pc' 'bundle resolves inherited profiles'
    assertContains "$output" 'Distribution .... pop' 'bundle reports target distribution'
    assertContains "$output" 'Release ......... 24.04' 'bundle reports target release'
    assertContains "$output" 'Architecture .... amd64' 'bundle reports target architecture'
    assertContains "$output" 'openssh-server' 'bundle includes raid server apt packages'
    assertContains "$output" 'snapraid' 'bundle includes SnapRAID'
    assertContains "$output" 'preview only; no files or packages downloaded' 'bundle is planning-only in stage 1'
    [[ ! -e "$target" ]] && {
        printf 'PASS  %s\n' 'bundle preview does not create output directory'
        ((passed += 1))
    } || {
        printf 'FAIL  %s\n' 'bundle preview unexpectedly created output directory'
        ((failed += 1))
    }
}

testBundleConfirmStillPlanningOnly() {
    local output target="$TMPDIR/raid-pc-bundle-confirm-test"
    rm -rf -- "$target"
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" bundle \
        --profile raid-pc \
        --output "$target" \
        --target-distribution pop \
        --target-release 24.04 \
        --target-architecture amd64 \
        --confirm)"
    assertContains "$output" 'preview only; no files or packages downloaded' 'stage 1 confirm cannot write a partial bundle'
    [[ ! -e "$target" ]] && {
        printf 'PASS  %s\n' 'stage 1 confirm remains non-destructive'
        ((passed += 1))
    } || {
        printf 'FAIL  %s\n' 'stage 1 confirm unexpectedly wrote bundle output'
        ((failed += 1))
    }
}

testBundleRejectsRootOutput() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" bundle \
        --profile raid-pc \
        --output / \
        --target-distribution pop \
        --target-release 24.04 \
        --target-architecture amd64 2>&1)" || status=$?
    [[ "$status" -ne 0 ]] && assertContains "$output" 'bundle output must not be /' 'bundle rejects root output path'
}

testBundleHelp
testBundleRequiresProfile
testBundleRequiresOutput
testRaidPcBundlePlan
testBundleConfirmStillPlanningOnly
testBundleRejectsRootOutput

printf '\n%d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
