#!/usr/bin/env bash
# Tests for hardwareSnapshot.sh. Sourced from runTests.sh.
#
# Every hardware command is a double on PATH, so the tests never read real
# sensors or disks and never call sudo.

_snapshotScript() {
    printf '%s' "$projectDir/hardwareSnapshot.sh"
}

_snapshotFakeBin() {
    local fakeBin="$testStateDir/snapshot-fake-bin"
    [[ -d "$fakeBin" ]] && { printf '%s' "$fakeBin"; return; }
    mkdir -p "$fakeBin"

    cat >"$fakeBin/hostname" <<'EOF'
#!/usr/bin/env bash
echo testhost
EOF
    cat >"$fakeBin/sudo" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == -n ]] || { echo "sudo called without -n" >&2; exit 1; }
shift
exec "$@"
EOF
    cat >"$fakeBin/sensors" <<'EOF'
#!/usr/bin/env bash
[[ "${1:-}" == -u ]] || { echo "k10temp-pci-00c3"; exit 0; }
cat <<'OUT'
k10temp-pci-00c3
Adapter: PCI adapter
Tctl:
  temp1_input: 54.125
Package id 0:
  temp2_input: 47.000
  temp2_max: 90.000

jc42-i2c-0-1b
Adapter: SMBus PIIX4 adapter port 0 at 0b00
temp1:
  temp1_input: 35.750
OUT
EOF
    # Two disks: a hard disk with a model and serial, and a disk with a serial
    # but no model, whose empty field must not shift the columns.
    cat >"$fakeBin/lsblk" <<'EOF'
#!/usr/bin/env bash
args="$*"
case "$args" in
    "-dn -o PATH,TYPE") printf '/dev/sda disk\n/dev/sdb disk\n/dev/loop0 loop\n' ;;
    "-dn -o MODEL /dev/sda") echo "WDC WD40" ;;
    "-dn -o SERIAL /dev/sda") echo "WD-SERIAL1" ;;
    "-dn -o ROTA /dev/sda") echo 1 ;;
    "-dn -o MODEL /dev/sdb") echo "" ;;
    "-dn -o SERIAL /dev/sdb") echo "SSD-SERIAL2" ;;
    "-dn -o ROTA /dev/sdb") echo 0 ;;
    *) echo "sda WDC WD40 WD-SERIAL1 3.6T disk sata" ;;
esac
EOF
    cat >"$fakeBin/smartctl" <<'EOF'
#!/usr/bin/env bash
case "$2" in
    /dev/sda) echo "194 Temperature_Celsius     0x0022   106   100   000    Old_age   Always       -       47" ;;
    /dev/sdb) echo "194 Temperature_Celsius     0x0022   067   050   000    Old_age   Always       -       33" ;;
esac
EOF
    cat >"$fakeBin/dmidecode" <<EOF
#!/usr/bin/env bash
echo "\${DMI_BIOS_VERSION:-Version: F1}"
EOF
    local name
    for name in hostnamectl lscpu lspci ip free; do
        printf '#!/usr/bin/env bash\necho "%s output"\n' "$name" >"$fakeBin/$name"
    done
    chmod +x "$fakeBin"/*
    printf '%s' "$fakeBin"
}

# Runs the tool with the doubles; a failing run is reported by the assertions
# rather than stopping the suite under set -e.
_snapshotRun() {
    PATH="$(_snapshotFakeBin):$PATH" "$(_snapshotScript)" "$@" 2>&1 || true
}

testHardwareSnapshotHelp() {
    local output
    output="$(_snapshotRun --help)"
    assertContains "$output" '--temps' 'hardwareSnapshot help documents --temps'
    assertContains "$output" '--version' 'hardwareSnapshot help documents --version'
}

testHardwareSnapshotVersion() {
    local output
    output="$(_snapshotRun --version)"
    assertContains "$output" "hardwareSnapshot $(tr -d '[:space:]' <"$projectDir/../VERSION")" 'hardwareSnapshot --version reports the repository version'
}

testHardwareSnapshotRejectsUnknownOption() {
    local status=0
    PATH="$(_snapshotFakeBin):$PATH" "$(_snapshotScript)" --bogus >/dev/null 2>&1 || status=$?
    if [[ "$status" -eq 2 ]]; then
        printf 'PASS  %s\n' 'hardwareSnapshot rejects an unknown option'
        ((passed += 1))
    else
        printf 'FAIL  %s (exit %s)\n' 'hardwareSnapshot rejects an unknown option' "$status"
        ((failed += 1))
    fi
}

testHardwareSnapshotSensorLabels() {
    local output
    output="$(_snapshotRun --temps)"
    assertContains "$output" 'hardwareSnapshot ' 'hardwareSnapshot --temps shows the version header'
    assertContains "$output" 'k10temp-pci-00c3: Tctl' 'sensor rows name the chip, not the Adapter line'
    assertContains "$output" 'k10temp-pci-00c3: Package id 0' 'unindented sensor labels are labels, not chips'
    assertContains "$output" 'jc42-i2c-0-1b: temp1' 'a chip after a blank line starts a new chip'
}

testHardwareSnapshotDiskColumns() {
    local output history
    output="$(_snapshotRun --temps)"
    assertContains "$output" 'HOT' 'a hard disk over 45°C is HOT'
    assertContains "$output" 'SSD-SERIAL2' 'a disk without a model is still listed'
    history="$(cat "$XDG_STATE_HOME/hardwareSnapshot/testhost/temperatures.csv" 2>/dev/null || true)"
    assertContains "$history" '"SSD-SERIAL2","disk",33,MEASURED' 'an empty model does not shift the history columns'
    assertContains "$history" '"WD-SERIAL1","WDC WD40",47,HOT' 'disk history records model, temperature and status'
}

testHardwareSnapshotDiff() {
    local output
    output="$(_snapshotRun)"
    assertContains "$output" 'BASELINE CREATED' 'the first snapshot creates a baseline'
    sleep 1
    output="$(_snapshotRun)"
    assertContains "$output" 'UNCHANGED' 'an identical snapshot is unchanged'
    sleep 1
    output="$(DMI_BIOS_VERSION='Version: F2' _snapshotRun)"
    assertContains "$output" 'Hardware configuration: CHANGED' 'a BIOS change is reported'
    output="$(_snapshotRun --diff)"
    assertContains "$output" '+Version: F2' '--diff shows the latest change'
}

hardwareSnapshotTestsRun() {
    testHardwareSnapshotHelp
    testHardwareSnapshotVersion
    testHardwareSnapshotRejectsUnknownOption
    testHardwareSnapshotSensorLabels
    testHardwareSnapshotDiskColumns
    testHardwareSnapshotDiff
}
