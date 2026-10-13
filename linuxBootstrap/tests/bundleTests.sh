#!/usr/bin/env bash
set -Eeuo pipefail

projectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
testTmpDir="${TMPDIR:-/tmp}"
passed=0
failed=0

pass() {
    printf 'PASS  %s\n' "$1"
    ((passed += 1))
}

fail() {
    printf 'FAIL  %s\n' "$1"
    ((failed += 1))
}

assertContains() {
    local output="$1" expected="$2" description="$3"
    if [[ "$output" == *"$expected"* ]]; then
        pass "$description"
    else
        printf 'FAIL  %s\nExpected: %s\nOutput:\n%s\n' "$description" "$expected" "$output"
        ((failed += 1))
    fi
}

assertFailsWith() {
    local description="$1" expected="$2"
    shift 2
    local output status=0
    output="$("$@" 2>&1)" || status=$?
    if [[ "$status" -eq 0 ]]; then
        fail "$description unexpectedly succeeded"
        return
    fi
    assertContains "$output" "$expected" "$description"
}

testBundleHelp() {
    local output
    output="$($projectDir/bootstrap.sh --help)"
    assertContains "$output" 'bundle' 'help documents bundle command'
    assertContains "$output" '--target-release VERSION' 'help documents bundle target release'
}

testBundleRequiresProfile() {
    assertFailsWith 'bundle requires one profile' 'bundle requires exactly one --profile NAME' \
        env NO_COLOR=1 "$projectDir/bootstrap.sh" bundle --output /tmp/test-bundle
}

testBundleRequiresOutput() {
    assertFailsWith 'bundle requires output path' 'bundle requires --output PATH' \
        env NO_COLOR=1 "$projectDir/bootstrap.sh" bundle --profile raid-pc
}

testRaidPcBundlePlan() {
    local output target="$testTmpDir/raid-pc-bundle-test"
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
    assertContains "$output" 'preview only; no files or packages downloaded' 'bundle preview is non-destructive'
    if [[ ! -e "$target" ]]; then
        pass 'bundle preview does not create output directory'
    else
        fail 'bundle preview unexpectedly created output directory'
    fi
}

testBundleRejectsRootOutput() {
    assertFailsWith 'bundle rejects root output path' 'bundle output must not be /' \
        env NO_COLOR=1 "$projectDir/bootstrap.sh" bundle \
        --profile raid-pc --output / \
        --target-distribution pop --target-release 24.04 --target-architecture amd64
}

testConfirmedBundleUsesMatchingTarget() {
    local fakeBin="$testTmpDir/linux-bootstrap-bundle-bin" target="$testTmpDir/raid-pc-bundle-confirm-test"
    local osRelease="$testTmpDir/linux-bootstrap-bundle-os-release" output
    rm -rf -- "$fakeBin" "$target"
    mkdir -p "$fakeBin"
    cat > "$osRelease" <<'EOF'
ID=pop
VERSION_ID="24.04"
EOF
    cat > "$fakeBin/dpkg" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == --print-architecture ]] && { printf 'amd64\n'; exit 0; }
exit 2
EOF
    cat > "$fakeBin/apt-get" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == download ]] || exit 2
printf 'fake package %s\n' "$2" > "${2}_1_amd64.deb"
EOF
    cat > "$fakeBin/dpkg-scanpackages" <<'EOF'
#!/usr/bin/env bash
for file in ./*.deb; do
    [[ -e "$file" ]] || continue
    printf 'Package: %s\nFilename: %s\n\n' "$(basename "$file" .deb)" "$file"
done
EOF
    chmod +x "$fakeBin/dpkg" "$fakeBin/apt-get" "$fakeBin/dpkg-scanpackages"

    output="$(PATH="$fakeBin:$PATH" BUNDLE_OS_RELEASE="$osRelease" NO_COLOR=1 \
        "$projectDir/bootstrap.sh" bundle \
        --profile raid-pc --output "$target" \
        --target-distribution pop --target-release 24.04 --target-architecture amd64 \
        --confirm)"
    assertContains "$output" 'create offline bootstrap bundle' 'confirmed bundle reports creation'
    [[ -f "$target/linuxBootstrapBundle/manifest.txt" ]] && pass 'confirmed bundle writes manifest' || fail 'confirmed bundle writes manifest'
    [[ -f "$target/linuxBootstrapBundle/SHA256SUMS" ]] && pass 'confirmed bundle writes checksums' || fail 'confirmed bundle writes checksums'
    [[ -f "$target/linuxBootstrapBundle/packages/Packages.gz" ]] && pass 'confirmed bundle writes apt repository index' || fail 'confirmed bundle writes apt repository index'
    [[ -f "$target/linuxBootstrapBundle/linuxBootstrap/bootstrap.sh" ]] && pass 'confirmed bundle copies bootstrap source' || fail 'confirmed bundle copies bootstrap source'
    grep -q '^distribution=pop$' "$target/linuxBootstrapBundle/manifest.txt" && pass 'manifest records distribution' || fail 'manifest records distribution'
    grep -q '^packages=.*snapraid' "$target/linuxBootstrapBundle/manifest.txt" && pass 'manifest records requested packages' || fail 'manifest records requested packages'
    rm -rf -- "$fakeBin" "$target" "$osRelease"
}

testConfirmedBundleRejectsMismatchedRelease() {
    local fakeBin="$testTmpDir/linux-bootstrap-bundle-mismatch-bin"
    local osRelease="$testTmpDir/linux-bootstrap-bundle-mismatch-os-release"
    rm -rf -- "$fakeBin"
    mkdir -p "$fakeBin"
    cat > "$osRelease" <<'EOF'
ID=pop
VERSION_ID="22.04"
EOF
    cat > "$fakeBin/dpkg" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == --print-architecture ]] && { printf 'amd64\n'; exit 0; }
exit 2
EOF
    chmod +x "$fakeBin/dpkg"
    assertFailsWith 'confirmed bundle rejects mismatched build release' 'target=24.04 current=22.04' \
        env PATH="$fakeBin:$PATH" BUNDLE_OS_RELEASE="$osRelease" NO_COLOR=1 \
        "$projectDir/bootstrap.sh" bundle \
        --profile raid-pc --output "$testTmpDir/should-not-exist-bundle" \
        --target-distribution pop --target-release 24.04 --target-architecture amd64 --confirm
    rm -rf -- "$fakeBin" "$osRelease" "$testTmpDir/should-not-exist-bundle"
}

testBundleHelp
testBundleRequiresProfile
testBundleRequiresOutput
testRaidPcBundlePlan
testBundleRejectsRootOutput
testConfirmedBundleUsesMatchingTarget
testConfirmedBundleRejectsMismatchedRelease

printf '\n%d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
