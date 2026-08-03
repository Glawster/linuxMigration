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

testHelp() {
    local output
    output="$($projectDir/bootstrap.sh --help)"
    assertContains "$output" '--profile NAME' 'help documents profiles'
}

testHostInheritance() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile laptop --dry-run)"
    assertContains "$output" 'Profiles ........ common, development, laptop' 'host inherits role profiles'
    assertContains "$output" 'set hostname to laptop' 'host supplies hostname'
}

testMultipleProfiles() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile common --profile media --dry-run)"
    assertContains "$output" 'Profiles ........ common, media' 'multiple profiles compose'
}

testMissingProfile() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile does-not-exist 2>&1)" || status=$?
    [[ "$status" -ne 0 ]] && assertContains "$output" 'profile not found' 'missing profile fails clearly' || {
        printf 'FAIL  missing profile returned success\n'; ((failed += 1));
    }
}

testInvalidIp() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --static-ip invalid 2>&1)" || status=$?
    [[ "$status" -ne 0 ]] && assertContains "$output" 'static IP must be IPv4 CIDR notation' 'invalid IP is rejected' || {
        printf 'FAIL  invalid IP returned success\n'; ((failed += 1));
    }
}

testInvalidIpOctet() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --static-ip 999.1.1.1/24 2>&1)" || status=$?
    [[ "$status" -ne 0 ]] && assertContains "$output" 'invalid octet' 'out-of-range IP octet is rejected' || {
        printf 'FAIL  out-of-range IP returned success\n'; ((failed += 1));
    }
}

testHelp
testHostInheritance
testMultipleProfiles
testMissingProfile
testInvalidIp
testInvalidIpOctet

printf '\n%d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
