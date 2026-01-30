#!/usr/bin/env bash
# Test dry run mode

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNPOD_TOOLS_DIR="$(dirname "$SCRIPT_DIR")"
LIB_DIR="$RUNPOD_TOOLS_DIR/lib"

# Setup test environment
export LOCAL_MODE=1
export SSH_TARGET="local"
export WORKSPACE_ROOT="$HOME/runpodLocalTest/workspace"
export RUNPOD_DIR="$WORKSPACE_ROOT/runpodTools"
export DRY_RUN=1
export DRY_PREFIX="[]"

# Create test workspace
mkdir -p "$WORKSPACE_ROOT"
mkdir -p "$RUNPOD_DIR"

# Source libraries
source "$LIB_DIR/common.sh"
source "$LIB_DIR/run.sh"
source "$LIB_DIR/workspace.sh"

echo "Testing dry run mode..."
echo

# Test 1: Read-only operations should execute in dry run
echo "Test 1: Read-only operations (should execute)"
if runCmdReadOnly test -d "$WORKSPACE_ROOT"; then
    echo "✓ runCmdReadOnly test passed"
else
    echo "✗ runCmdReadOnly test failed"
fi

output=$(runShReadOnly "echo 'Hello from read-only'")
if [[ "$output" == *"Hello from read-only"* ]]; then
    echo "✓ runShReadOnly echo passed"
else
    echo "✗ runShReadOnly echo failed"
fi

# Test 2: Write operations should NOT execute in dry run
echo
echo "Test 2: Write operations (should show dry run message)"
runCmd mkdir -p "$WORKSPACE_ROOT/test_dir"
runSh "echo 'test' > '$WORKSPACE_ROOT/test_file'"

# Test 3: State file should be unique per target
echo
echo "Test 3: State file naming (local mode)"
STATE_FILE=$(getStateFileName)
echo "State file: $STATE_FILE"
# In local mode, basename should be exactly "state.env"
if [[ "$(basename "$STATE_FILE")" == "state.env" ]]; then
    echo "✓ State file uses correct naming"
else
    echo "✗ State file naming incorrect"
fi

# Test 4: State file with SSH_TARGET
export SSH_TARGET="root@192.168.1.100"
export SSH_PORT="40023"
STATE_FILE=$(getStateFileName)
echo
echo "Test 4: State file naming (remote mode)"
echo "State file: $STATE_FILE"
if [[ "$STATE_FILE" == *"state_root_192_168_1_100_40023.env"* ]]; then
    echo "✓ State file uses unique naming for remote target"
else
    echo "✗ State file naming incorrect for remote target"
fi

echo
echo "Dry run test complete!"
