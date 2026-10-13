#!/usr/bin/env bash

imageSourceValidate() {
    local iso="$1" report systemArea
    [[ -f "$iso" ]] || { logError "image source ISO not found: $iso"; return 2; }
    command -v xorriso >/dev/null 2>&1 || { logError "xorriso is required to build an offline installer image"; return 2; }

    report="$(xorriso -indev "$iso" -report_el_torito as_mkisofs 2>&1)"
    systemArea="$(xorriso -indev "$iso" -report_system_area plain 2>&1)"

    [[ "$report" == *"-b '/isolinux/isolinux.bin'"* ]] || { logError "unsupported ISO: legacy BIOS boot image not found"; return 2; }
    [[ "$report" == *"-e '/boot/grub/efi.img'"* ]] || { logError "unsupported ISO: UEFI boot image not found"; return 2; }
    [[ "$report" == *"-isohybrid-gpt-basdat"* ]] || { logError "unsupported ISO: hybrid GPT boot metadata not found"; return 2; }
    [[ "$systemArea" == *"MBR isohybrid"* && "$systemArea" == *"GPT"* ]] || {
        logError "unsupported ISO: expected isohybrid MBR/GPT system area"
        return 2
    }
}

imageBundleValidate() {
    local bundle="$1"
    [[ -d "$bundle" ]] || { logError "image bundle directory not found: $bundle"; return 2; }
    [[ -f "$bundle/manifest.txt" ]] || { logError "image bundle manifest not found: $bundle/manifest.txt"; return 2; }
    [[ -f "$bundle/SHA256SUMS" ]] || { logError "image bundle checksums not found: $bundle/SHA256SUMS"; return 2; }
    [[ -d "$bundle/packages" ]] || { logError "image bundle packages directory not found: $bundle/packages"; return 2; }
    [[ -d "$bundle/linuxBootstrap" ]] || { logError "image bundle bootstrap source not found: $bundle/linuxBootstrap"; return 2; }
    (
        cd "$bundle"
        sha256sum -c SHA256SUMS >/dev/null
    ) || { logError "image bundle checksum validation failed"; return 2; }
}

imagePlan() {
    local iso="$1" bundle="$2" output="$3"
    [[ -n "$iso" ]] || { logError "image requires --iso PATH"; return 2; }
    [[ -n "$bundle" ]] || { logError "image requires --bundle PATH"; return 2; }
    [[ -n "$output" ]] || { logError "image requires --output PATH"; return 2; }
    [[ "$output" != "$iso" ]] || { logError "image output must not overwrite source ISO"; return 2; }

    printf 'Image plan\n'
    printf '  Source ISO ...... %s\n' "$iso"
    printf '  Bundle .......... %s\n' "$bundle"
    printf '  ISO destination . /raid-pc/linuxBootstrapBundle\n'
    printf '  Output .......... %s\n' "$output"
    if [[ "$dryRun" == 1 ]]; then
        printf '  Action .......... preview only; source ISO remains unchanged\n'
    else
        printf '  Action .......... create bootable offline installer ISO\n'
    fi
}

imageCreate() {
    local iso="$1" bundle="$2" output="$3" outputDir
    imageSourceValidate "$iso"
    imageBundleValidate "$bundle"
    [[ ! -e "$output" ]] || { logError "image output already exists: $output"; return 2; }

    outputDir="$(dirname "$output")"
    mkdir -p "$outputDir"

    xorriso \
        -indev "$iso" \
        -outdev "$output" \
        -boot_image any replay \
        -map "$bundle" /raid-pc/linuxBootstrapBundle \
        -commit

    [[ -s "$output" ]] || { logError "image output was not created: $output"; return 2; }
    xorriso -indev "$output" -ls /raid-pc/linuxBootstrapBundle >/dev/null
    imageSourceValidate "$output"
    logSuccess "offline bootstrap installer ISO created: $output"
}

imageRunAction() {
    local iso="$1" bundle="$2" output="$3"
    imagePlan "$iso" "$bundle" "$output"
    [[ "$dryRun" == 1 ]] || imageCreate "$iso" "$bundle" "$output"
}
