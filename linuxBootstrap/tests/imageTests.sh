#!/usr/bin/env bash
set -Eeuo pipefail

projectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
testTmpDir="${TMPDIR:-/tmp}"
passed=0
failed=0

pass() { printf 'PASS  %s\n' "$1"; ((passed += 1)); }
fail() { printf 'FAIL  %s\n' "$1"; ((failed += 1)); }
assertContains() { local output="$1" expected="$2" description="$3"; [[ "$output" == *"$expected"* ]] && pass "$description" || { printf 'FAIL  %s\nExpected: %s\nOutput:\n%s\n' "$description" "$expected" "$output"; ((failed += 1)); }; }
assertFailsWith() { local description="$1" expected="$2" output status=0; shift 2; output="$("$@" 2>&1)" || status=$?; [[ "$status" -ne 0 ]] || { fail "$description unexpectedly succeeded"; return; }; assertContains "$output" "$expected" "$description"; }

testImageHelp() {
    local output
    output="$($projectDir/bootstrap.sh --help)"
    assertContains "$output" 'image' 'help documents image command'
    assertContains "$output" '--iso PATH' 'help documents image source ISO'
    assertContains "$output" '--bundle PATH' 'help documents image bundle'
}

testImageRequiresArguments() {
    assertFailsWith 'image requires profile' 'image requires exactly one --profile NAME' env NO_COLOR=1 "$projectDir/bootstrap.sh" image --iso source.iso --bundle bundle --output output.iso
    assertFailsWith 'image requires source ISO' 'image requires --iso PATH' env NO_COLOR=1 "$projectDir/bootstrap.sh" image --profile raid-pc --bundle bundle --output output.iso
    assertFailsWith 'image requires bundle' 'image requires --bundle PATH' env NO_COLOR=1 "$projectDir/bootstrap.sh" image --profile raid-pc --iso source.iso --output output.iso
    assertFailsWith 'image requires output' 'image requires --output PATH' env NO_COLOR=1 "$projectDir/bootstrap.sh" image --profile raid-pc --iso source.iso --bundle bundle
}

testImagePreview() {
    local output target="$testTmpDir/linux-bootstrap-image-preview.iso"
    rm -f -- "$target"
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" image --profile raid-pc --iso source.iso --bundle bundle --output "$target")"
    assertContains "$output" 'Source ISO ...... source.iso' 'image preview reports source ISO'
    assertContains "$output" 'ISO destination . /raid-pc/linuxBootstrapBundle' 'image preview reports embedded bundle path'
    assertContains "$output" 'preview only; source ISO remains unchanged' 'image preview is non-destructive'
    [[ ! -e "$target" ]] && pass 'image preview does not create output ISO' || fail 'image preview does not create output ISO'
}

testImageRejectsSourceOverwrite() {
    assertFailsWith 'image rejects source overwrite' 'image output must not overwrite source ISO' env NO_COLOR=1 "$projectDir/bootstrap.sh" image --profile raid-pc --iso same.iso --bundle bundle --output same.iso
}

testImageHelp
testImageRequiresArguments
testImagePreview
testImageRejectsSourceOverwrite

printf '\n%d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
