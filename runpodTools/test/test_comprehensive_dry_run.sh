#!/usr/bin/env bash
# Comprehensive test for dry run mode with remote target

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNPOD_TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="$RUNPOD_TOOLS_DIR/lib"

echo "==================================="
echo "Comprehensive Dry Run Mode Test"
echo "==================================="
echo

# Test 1: Local mode
echo "Test 1: Local Mode State File"
echo "------------------------------"
export LOCAL_MODE=1
export SSH_TARGET="local"
export WORKSPACE_ROOT="$HOME/runpodLocalTest/workspace"
export RUNPOD_DIR="$WORKSPACE_ROOT/runpodTools"
export DRY_RUN=1
export DRY_PREFIX="[]"

mkdir -p "$WORKSPACE_ROOT"
mkdir -p "$RUNPOD_DIR"

source "$LIB_DIR/run.sh"
source "$LIB_DIR/common.sh"
source "$LIB_DIR/workspace.sh"

STATE_FILE=$(getStateFileName)
echo "State file (local): $STATE_FILE"
# Basename should be exactly "state.env" in local mode
if [[ "$(basename "$STATE_FILE")" == "state.env" ]]; then
    echo "✓ Local mode uses simple state file"
else
    echo "✗ Local mode state file naming incorrect"
fi
echo

# Test 2: Remote mode with target 1
echo "Test 2: Remote Mode - Target 1"
echo "------------------------------"
export SSH_TARGET="root@192.168.1.100"
export SSH_PORT="40023"
STATE_FILE=$(getStateFileName)
echo "State file (remote 1): $STATE_FILE"
if [[ "$STATE_FILE" == *"state_root_192_168_1_100_40023.env"* ]]; then
    echo "✓ Remote mode uses unique state file for target 1"
else
    echo "✗ Remote mode state file naming incorrect for target 1"
fi
echo

# Test 3: Remote mode with target 2 (different)
echo "Test 3: Remote Mode - Target 2"
echo "------------------------------"
export SSH_TARGET="root@213.192.2.88"
export SSH_PORT="50044"
STATE_FILE=$(getStateFileName)
echo "State file (remote 2): $STATE_FILE"
if [[ "$STATE_FILE" == *"state_root_213_192_2_88_50044.env"* ]]; then
    echo "✓ Remote mode uses unique state file for target 2"
else
    echo "✗ Remote mode state file naming incorrect for target 2"
fi
echo

# Test 4: Verify different targets have different state files
echo "Test 4: State File Uniqueness"
echo "------------------------------"
export SSH_TARGET="root@192.168.1.100"
export SSH_PORT="40023"
STATE_FILE_1=$(getStateFileName)

export SSH_TARGET="root@213.192.2.88"
export SSH_PORT="50044"
STATE_FILE_2=$(getStateFileName)

if [[ "$STATE_FILE_1" != "$STATE_FILE_2" ]]; then
    echo "✓ Different targets have different state files"
    echo "  Target 1: $(basename "$STATE_FILE_1")"
    echo "  Target 2: $(basename "$STATE_FILE_2")"
else
    echo "✗ State files not unique"
fi
echo

# Test 5: Read-only operations in dry run
echo "Test 5: Read-Only Operations"
echo "------------------------------"
export LOCAL_MODE=1
export SSH_TARGET="local"
export DRY_RUN=1

if runCmdReadOnly test -d "$WORKSPACE_ROOT"; then
    echo "✓ runCmdReadOnly executes in dry run"
else
    echo "✗ runCmdReadOnly failed"
fi

output=$(runShReadOnly "echo 'test output'" 2>&1)
if [[ "$output" == *"test output"* ]]; then
    echo "✓ runShReadOnly executes and returns output"
else
    echo "✗ runShReadOnly failed"
fi
echo

# Test 6: Write operations blocked in dry run
echo "Test 6: Write Operations (Should Show [] Prefix)"
echo "------------------------------"
TEST_DIR="$WORKSPACE_ROOT/test_write_blocked_$(date +%s)"
output=$(runCmd mkdir -p "$TEST_DIR" 2>&1)
if [[ "$output" == *"[]"* ]]; then
    if [[ ! -d "$TEST_DIR" ]]; then
        echo "✓ Write operations show [] prefix and don't execute"
        echo "  Output: $output"
    else
        echo "✗ Write operations not properly blocked - directory was created"
    fi
else
    echo "✗ Write operations not showing [] prefix"
fi
echo

echo "==================================="
echo "All Tests Complete!"
echo "==================================="
