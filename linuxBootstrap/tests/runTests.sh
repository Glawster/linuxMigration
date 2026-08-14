#!/usr/bin/env bash
set -Eeuo pipefail

projectDir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
testStateDir="$(mktemp -d "${TMPDIR:-/tmp}/linux-bootstrap-tests.XXXXXX")"
export XDG_STATE_HOME="$testStateDir"
trap 'rm -rf -- "$testStateDir"' EXIT
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
    assertContains "$output" 'profile validate' 'help documents profile subcommands'
}

testInstallCommand() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" install --profile media)"
    assertContains "$output" 'Command ......... install' 'install subcommand dispatches configuration'
    assertContains "$output" 'Profiles ........ media' 'install subcommand loads requested profile'
}

testLogging() {
    local logPath output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile list)"
    logPath="$(find "$testStateDir/linuxBootstrap" -type f -name 'bootstrap-*.log' | sort | tail -n 1)"
    [[ -n "$logPath" && -f "$logPath" ]] || { printf 'FAIL  bootstrap did not create a log file\n'; ((failed += 1)); return; }
    assertContains "$(<"$logPath")" 'linux-bootstrap profile starting' 'log file captures bootstrap output'
    assertContains "$output" 'log file:' 'terminal output reports log location'
}

testHostInheritance() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile laptop)"
    assertContains "$output" 'Profiles ........ common, development, laptop' 'host inherits role profiles'
    assertContains "$output" 'set hostname to laptop' 'host supplies hostname'
}

testTvPcHostname() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile show tv-pc)"
    assertContains "$output" 'Hostname: TV-PC' 'TV PC profile uses actual hostname'
    assertContains "$output" 'Expected IP: 192.168.1.201' 'TV PC records expected reserved IP'
}

testMultipleProfiles() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile common --profile media)"
    assertContains "$output" 'Profiles ........ common, media' 'multiple profiles compose'
}

testMasterHost() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile common)"
    assertContains "$output" 'Config master ... main-pc (Andy-PC)' 'master host is declared explicitly'
}

testMasterExpectedIp() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile main-pc)"
    assertContains "$output" 'Expected IP ..... 192.168.1.200 (DHCP reservation)' 'master records expected reserved IP'
}

testOfficeFlatpak() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" --profile office)"
    assertContains "$output" 'install system Flatpak: org.libreoffice.LibreOffice' 'office profile installs current LibreOffice Flatpak'
}

testProfileCommands() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile list)"
    assertContains "$output" 'main-pc (master: Andy-PC)' 'profile list identifies master'
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile show main-pc)"
    assertContains "$output" 'flatpak: org.libreoffice.LibreOffice' 'profile show prints merged configuration'
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile show gaming)"
    assertContains "$output" 'dcs.installDir: /mnt/games/dcs' 'profile show prints DCS configuration'
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile show wow)"
    assertContains "$output" 'wow.installDir: /mnt/games/wow' 'profile show prints WoW configuration'
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile validate)"
    assertContains "$output" 'all profiles are valid' 'profile validate checks repository profiles'
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile add test-role)"
    assertContains "$output" 'would create role profile: test-role' 'profile add previews creation by default'
    [[ ! -e "$projectDir/profiles/test-role.yaml" ]] || { printf 'FAIL  profile add preview created a file\n'; ((failed += 1)); }
}

testUpdateClassification() {
    local output
    output="$({
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/packages.sh"
        apt-get() {
            if [[ "$1" == -s ]]; then printf 'Inst git [1] (2 repo)\nInst gimp [1] (2 repo)\nInst libc6 [1] (2 repo)\n'; fi
        }
        apt-mark() { printf 'git\ngimp\n'; }
        flatpak() {
            if [[ "$1" == remote-ls ]]; then printf 'org.libreoffice.LibreOffice\norg.blender.Blender\n'; fi
        }
        sudo() { return 0; }
        dryRun=1
        profileFlatpakPackages=(org.libreoffice.LibreOffice)
        packagesUpdate git
    })"
    assertContains "$output" 'managed    git' 'update classifies managed apt package'
    assertContains "$output" 'unmanaged  gimp' 'update classifies unmanaged manual apt package'
    assertContains "$output" 'system     libc6' 'update classifies apt dependency'
    assertContains "$output" 'managed    org.libreoffice.LibreOffice' 'update classifies managed Flatpak'
    assertContains "$output" 'unmanaged  org.blender.Blender' 'update classifies unmanaged Flatpak'
}

testFlatpakConfirmApplies() {
    local output
    output="$({
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/packages.sh"
        flatpak() {
            case "$1" in
                remote-list) printf 'flathub\n' ;;
                info) return 1 ;;
                install) printf 'FLATPAK_CALL %s\n' "$*" ;;
            esac
        }
        dryRun=0
        packagesFlatpakApply org.libreoffice.LibreOffice
    })"
    assertContains "$output" 'FLATPAK_CALL install --system --noninteractive -y flathub org.libreoffice.LibreOffice' 'confirm mode executes Flatpak installation'
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

testNestedPackageProfile() {
    local output
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" profile show andy-pc)"
    assertContains "$output" 'flatpak: com.rustdesk.RustDesk' 'nested package lists merge with current profiles'
}

testHostsFileRender() {
    local output source target
    source="$testStateDir/hosts"
    target="$testStateDir/hosts-rendered"
    printf '127.0.0.1 localhost\n# BEGIN linux-bootstrap hosts\n192.0.2.1 old\n# END linux-bootstrap hosts\n' > "$source"
    source "$projectDir/lib/networking.sh"
    hostsFileRender "$source" "$target" '192.0.2.10 host-a' '192.0.2.20 host-b'
    output="$(<"$target")"
    assertContains "$output" '127.0.0.1 localhost' 'hosts rendering preserves unmanaged entries'
    assertContains "$output" '192.0.2.20 host-b' 'hosts rendering replaces managed entries'
}

testNfsMountRender() {
    local output source target
    source="$testStateDir/fstab"
    target="$testStateDir/fstab-rendered"
    printf 'UUID=root / ext4 defaults 0 1\n' > "$source"
    source "$projectDir/lib/nfs.sh"
    _nfsMountsFileRender "$source" "$target" 'server:/media /mnt/media ro,_netdev,nofail'
    output="$(<"$target")"
    assertContains "$output" 'UUID=root / ext4 defaults 0 1' 'NFS rendering preserves unmanaged fstab entries'
    assertContains "$output" 'server:/media /mnt/media nfs4 ro,_netdev,nofail 0 0' 'NFS rendering adds managed mounts'
}

testCapturePreview() {
    local captureHome output
    captureHome="$testStateDir/capture-home"
    mkdir -p "$captureHome"
    HOME="$captureHome" git config --global user.name 'Example User'
    HOME="$captureHome" git config --global user.email 'example@example.com'
    HOME="$captureHome" git config --global init.defaultBranch main
    output="$(HOME="$captureHome" NO_COLOR=1 "$projectDir/bootstrap.sh" capture --profile common)"
    assertContains "$output" 'would capture global Git configuration in profile: common' 'capture previews Git profile changes'
    assertContains "$output" 'Command ......... capture' 'capture summary identifies its command'
}

testCaptureProfileRender() {
    local output source target
    source="$testStateDir/capture-profile.yaml"
    target="$testStateDir/capture-rendered.yaml"
    printf 'name: example\n\ngit:\n  name: Old Name\n  defaultBranch: master\n\nservices:\n  - ssh\n' > "$source"
    source "$projectDir/lib/capture.sh"
    captureGitProfileRender "$source" "$target" 'Example User' 'example@example.com' main
    output="$(<"$target")"
    assertContains "$output" 'name: Example User' 'capture replaces the Git name'
    assertContains "$output" 'email: example@example.com' 'capture records the Git email'
    assertContains "$output" 'defaultBranch: main' 'capture records the default branch'
    assertContains "$output" '  - ssh' 'capture preserves unrelated profile content'
}

testCaptureRequiresProfile() {
    local output status=0
    output="$(NO_COLOR=1 "$projectDir/bootstrap.sh" capture 2>&1)" || status=$?
    [[ "$status" -eq 2 ]] && assertContains "$output" 'capture requires exactly one --profile NAME' 'capture requires an explicit destination' || {
        printf 'FAIL  capture without a profile returned an unexpected status\n'; ((failed += 1));
    }
}

testCaptureConfirmWritesProfile() {
    local captureHome captureProject output
    captureHome="$testStateDir/capture-confirm-home"
    captureProject="$testStateDir/capture-project"
    mkdir -p "$captureHome" "$captureProject/profiles/hosts"
    printf 'name: common\n\ngit:\n  defaultBranch: master\n' > "$captureProject/profiles/common.yaml"
    HOME="$captureHome" git config --global user.name 'Captured User'
    HOME="$captureHome" git config --global user.email 'captured@example.com'
    HOME="$captureHome" git config --global init.defaultBranch main
    HOME="$captureHome" bash -c '
        projectDir="$1"
        source "$2/lib/logging.sh"
        source "$2/lib/common.sh"
        source "$2/lib/profiles.sh"
        source "$2/lib/capture.sh"
        dryRun=0
        captureGitProfile common
    ' _ "$captureProject" "$projectDir"
    output="$(<"$captureProject/profiles/common.yaml")"
    assertContains "$output" 'name: Captured User' 'confirmed capture writes the Git name'
    assertContains "$output" 'email: captured@example.com' 'confirmed capture writes the Git email'
    assertContains "$output" 'defaultBranch: main' 'confirmed capture writes the default branch'
}

testDcsDisabled() {
    local output
    output="$({
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        verbose=1
        dcsApply false /mnt/games/dcs false
    })"
    assertContains "$output" 'DCS: disabled by profile' 'DCS does nothing unless explicitly enabled'
}

testDcsEnabledDryRun() {
    local output
    output="$({
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        umu-run() { return 0; }
        dryRun=1
        dcsApply true "$testStateDir/custom-dcs" false
    })"
    assertContains "$output" "would create DCS installation directory: $testStateDir/custom-dcs" 'DCS dry-run reports a custom installation path'
    assertContains "$output" 'would run Eagle Dynamics installer' 'DCS dry-run previews the standalone installer'
}

testDcsRunnerChecksum() {
    source "$projectDir/lib/dcs.sh"
    if [[ "$dcsUmuArchiveSha256" =~ ^[0-9a-f]{64}$ ]]; then
        printf 'PASS  %s\n' 'DCS UMU archive uses a valid SHA-256 digest'
        ((passed += 1))
    else
        printf 'FAIL  %s\n' 'DCS UMU archive checksum is malformed'
        ((failed += 1))
    fi
}

testDcsInstallerUrlRead() {
    local output
    source "$projectDir/lib/dcs.sh"
    output="$(printf '%s\n' '<a href="/upload/current/DCS_World_web.exe" class="btn">Download</a>' | _dcsInstallerUrlRead)"
    [[ "$output" == '/upload/current/DCS_World_web.exe' ]] && {
        printf 'PASS  %s\n' 'DCS discovers the current Eagle Dynamics installer link format'
        ((passed += 1))
        return
    }
    printf 'FAIL  %s\nExpected installer path, got: %s\n' 'DCS installer URL parser' "$output"
    ((failed += 1))
}

testDcsMissingPrerequisite() {
    local output status=0
    output="$({
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        command() { [[ "$2" == curl ]] && return 1; builtin command "$@"; }
        dryRun=1
        dcsApply true "$testStateDir/missing-prerequisite-dcs" false
    } 2>&1)" || status=$?
    [[ "$status" -eq 127 ]] && assertContains "$output" 'required command not found: curl' 'DCS reports missing prerequisites' || {
        printf 'FAIL  DCS missing prerequisite returned an unexpected status\n'; ((failed += 1));
    }
}

testDcsExistingIdempotent() {
    local dcsHome installDir output firstChanges secondChanges
    dcsHome="$testStateDir/dcs-home"
    installDir="$testStateDir/existing-dcs"
    mkdir -p "$dcsHome/data/Steam/compatibilitytools.d/GE-Proton-test" "$installDir/bin"
    : > "$installDir/bin/DCS.exe"
    : > "$installDir/bin/DCS_updater.exe"
    output="$({
        HOME="$dcsHome"
        XDG_DATA_HOME="$dcsHome/data"
        XDG_CACHE_HOME="$dcsHome/cache"
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        umu-run() { return 0; }
        dryRun=0
        dcsApply true "$installDir" false
        firstChanges="$summaryChanged"
        dcsApply true "$installDir" false
        secondChanges="$summaryChanged"
        printf 'COUNTS %s %s\n' "$firstChanges" "$secondChanges"
    })"
    assertContains "$output" "DCS: installation found at $installDir" 'DCS detects an existing standalone installation'
    assertContains "$output" 'COUNTS 6 6' 'repeated DCS execution leaves launchers and drive mapping unchanged'
    [[ "$(readlink "$dcsHome/data/dcs/prefix/dosdevices/g:")" == "$(dirname "$installDir")" ]] && {
        printf 'PASS  %s\n' 'DCS maps Wine drive G: to the configured games directory'
        ((passed += 1))
    } || {
        printf 'FAIL  %s\n' 'DCS did not create the expected Wine drive mapping'
        ((failed += 1))
    }
}

testDcsStatus() {
    local dcsHome installDir output
    dcsHome="$testStateDir/dcs-status-home"
    installDir="$testStateDir/status-dcs"
    mkdir -p "$dcsHome/data/dcs/prefix" "$installDir/bin" "$dcsHome/.local/bin"
    : > "$installDir/bin/DCS.exe"
    : > "$installDir/bin/DCS_updater.exe"
    : > "$dcsHome/.local/bin/dcs-world"
    chmod 755 "$dcsHome/.local/bin/dcs-world"
    output="$({
        HOME="$dcsHome"
        XDG_DATA_HOME="$dcsHome/data"
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        umu-run() { return 0; }
        requestedCommand=status
        dcsApply true "$installDir" true
    })"
    assertContains "$output" 'DCS: enabled by profile' 'DCS status reports profile enablement'
    assertContains "$output" 'DCS: DCS_updater.exe exists' 'DCS status reports the Eagle Dynamics updater'
    assertContains "$output" 'DCS: VR is enabled' 'DCS status reports separable VR configuration'
}

testWowDisabled() {
    local output
    output="$({
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        source "$projectDir/lib/wow.sh"
        verbose=1
        wowApply false /mnt/games/wow
    })"
    assertContains "$output" 'WoW: disabled by profile' 'WoW does nothing unless explicitly enabled'
}

testWowDryRun() {
    local wowHome output
    wowHome="$testStateDir/wow-home"
    mkdir -p "$wowHome/data/Steam/compatibilitytools.d/GE-Proton-test"
    output="$({
        HOME="$wowHome"
        XDG_DATA_HOME="$wowHome/data"
        XDG_CACHE_HOME="$wowHome/cache"
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        source "$projectDir/lib/wow.sh"
        umu-run() { return 0; }
        dryRun=1
        wowApply true "$testStateDir/games/wow"
    })"
    assertContains "$output" 'would map WoW Wine drive G:' 'WoW dry-run previews the G: drive mapping'
    assertContains "$output" 'would download official Battle.net installer' 'WoW dry-run previews the official installer'
    assertContains "$output" 'choose G:\wow' 'WoW reports the configured Battle.net game path'
}

testWowStatus() {
    local wowHome output
    wowHome="$testStateDir/wow-status-home"
    mkdir -p "$wowHome/data/Steam/compatibilitytools.d/GE-Proton-test"
    output="$({
        HOME="$wowHome"
        XDG_DATA_HOME="$wowHome/data"
        source "$projectDir/lib/logging.sh"
        source "$projectDir/lib/common.sh"
        source "$projectDir/lib/dcs.sh"
        source "$projectDir/lib/wow.sh"
        umu-run() { return 0; }
        requestedCommand=status
        wowApply true "$testStateDir/games/wow"
    })"
    assertContains "$output" 'WoW: enabled by profile' 'WoW status reports profile enablement'
    assertContains "$output" 'WoW: GE-Proton runner available' 'WoW status reports the compatibility runner'
    assertContains "$output" 'WoW: installation missing' 'WoW status reports a missing game installation'
}

testHelp
testInstallCommand
testLogging
testHostInheritance
testTvPcHostname
testMultipleProfiles
testMasterHost
testMasterExpectedIp
testOfficeFlatpak
testFlatpakConfirmApplies
testProfileCommands
testUpdateClassification
testMissingProfile
testInvalidIp
testInvalidIpOctet
testNestedPackageProfile
testHostsFileRender
testNfsMountRender
testCapturePreview
testCaptureProfileRender
testCaptureRequiresProfile
testCaptureConfirmWritesProfile
testDcsDisabled
testDcsEnabledDryRun
testDcsRunnerChecksum
testDcsInstallerUrlRead
testDcsMissingPrerequisite
testDcsExistingIdempotent
testDcsStatus
testWowDisabled
testWowDryRun
testWowStatus

printf '\n%d passed, %d failed\n' "$passed" "$failed"
((failed == 0))
