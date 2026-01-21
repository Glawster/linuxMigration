# RunPod Modular Bootstrap

This directory contains a modular, idempotent bootstrap system for RunPod instances.

## Directory Structure

```
runpodTools/
  lib/                      # Reusable library functions
    common.sh               # Logging, run, die, timestamp helpers
    ssh.sh                  # SSH command builders, remote execution
    apt.sh                  # APT package management
    conda.sh                # Conda environment setup
    git.sh                  # Git repository management (idempotent)
    workspace.sh            # Common paths, state tracking
    diagnostics.sh          # System diagnostics
  steps/                    # Individual setup steps
    10_diagnostics.sh       # System diagnostics
    20_base_tools.sh        # Base system tools via apt
    30_conda.sh             # Miniconda setup
    40_comfyui.sh           # ComfyUI setup
    50_kohya.sh             # Kohya SS setup
    60_upload_models.sh     # Model upload instructions
  logs/                     # Bootstrap logs (auto-created)
  runpodBootstrap.sh        # Remote-side step runner
  runpodFromSSH.sh          # Local-side orchestrator
  startComfyUI.sh           # Start ComfyUI in tmux
  generateUploadScript.sh   # Generate uploadModels.sh
```

## Usage

### Execution Modes

This system supports two execution modes:

#### Mode 1: Remote Execution via SSH (Recommended)

Run the bootstrap script **locally on your machine** and execute all commands on the remote RunPod instance via SSH as root:

```bash
./runpodTools/runpodFromSSH.sh ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```

**How it works:**
- Your local machine orchestrates the setup
- All commands (apt, git, conda, pip) execute on the remote RunPod instance via SSH
- Libraries transparently detect SSH_TARGET and use remote execution
- No files need to be copied to the remote instance
- Safe to disconnect and reconnect (logs preserved on remote)

**Benefits:**
- Control from your local machine
- No need to manage scripts on the remote instance
- Can monitor progress locally
- Easy to rerun or modify steps

#### Mode 2: Direct Local Execution

Run the bootstrap script **directly on the RunPod instance**:

```bash
bash /workspace/runpodTools/runpodBootstrap.sh
```

**How it works:**
- SSH into the RunPod instance first
- Run the script directly on the remote machine
- All commands execute locally on the instance
- SSH_TARGET is not set, so libraries use local execution

**When to use:**
- Already have SSH access and prefer running directly
- Debugging or testing individual steps
- Don't want to maintain SSH connection from local machine

### Quick Start

```bash
# Basic setup with ComfyUI (default)
./runpodTools/runpodFromSSH.sh ssh root@HOST -p PORT -i ~/.ssh/id_ed25519

# With Kohya
./runpodTools/runpodFromSSH.sh --kohya ssh root@HOST -p PORT -i ~/.ssh/id_ed25519

# Dry run to see what would happen
./runpodTools/runpodFromSSH.sh --dry-run ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```

### Advanced Usage

```bash

# List available steps
./runpodFromSSH.sh --list ssh root@HOST -p PORT -i KEY

# Run only a specific step
./runpodFromSSH.sh --only 40_comfyui ssh root@HOST -p PORT -i KEY

# Start from a specific step
./runpodFromSSH.sh --from 30_conda ssh root@HOST -p PORT -i KEY

# Skip a step
./runpodFromSSH.sh --skip 20_base_tools ssh root@HOST -p PORT -i KEY

# Force rerun (ignore state file)
./runpodFromSSH.sh --force ssh root@HOST -p PORT -i KEY

# Copy scripts only, don't run
./runpodFromSSH.sh --no-run ssh root@HOST -p PORT -i KEY
```

### Direct Remote Execution

If you're already on the RunPod instance:

```bash
# Run all steps
bash /workspace/runpodTools/runpodBootstrap.sh

# With options
bash /workspace/runpodTools/runpodBootstrap.sh --kohya --force

# List steps
bash /workspace/runpodTools/runpodBootstrap.sh --list

# Run specific step
bash /workspace/runpodTools/runpodBootstrap.sh --only 40_comfyui
```

## Features

### Idempotent by Design

Each step checks if work is already done:
- If desired state exists → skip
- If exists but wrong → repair or move aside
- State tracked in `/workspace/runpodTools/state.env`
- Use `--force` to ignore state and rerun

### Smart Logging

- All output tee'd to `/workspace/runpodTools/logs/bootstrap.TIMESTAMP.log`
- Survives disconnects
- Easy debugging

### Modular Steps

Each step is independent and can be:
- Run individually (`--only`)
- Skipped (`--skip`)
- Started from (`--from`)
- Listed (`--list`)

### Safe Remote Operations

- Idempotent git clones (auto-pull if exists)
- Moves aside conflicting directories with timestamps
- Non-interactive apt (no hangs)
- Conda channel resilience

## Starting ComfyUI

After bootstrap completes:

```bash
bash /workspace/runpodTools/startComfyUI.sh 8188
```

Or from the bootstrap scripts (automatic when using `--comfyui`).

## Uploading Models

Generate the upload script:

```bash
./generateUploadScript.sh ./uploadModels.sh
```

Then use it:

```bash
./uploadModels.sh ssh root@HOST -p PORT -i KEY
```

Or with custom model root:

```bash
./uploadModels.sh --model-root /path/to/models ssh root@HOST -p PORT -i KEY
```

## State File

Located at `/workspace/runpodTools/state.env`, tracks completed steps:

```bash
DONE_DIAGNOSTICS=1
DONE_BASE_TOOLS=1
DONE_CONDA=1
DONE_COMFYUI=1
```

Delete to force rerun all steps, or use `--force` flag.

## Development

### Adding a New Step

1. Create `steps/XX_stepname.sh`
2. Follow the template:

```bash
#!/usr/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

source "$LIB_DIR/common.sh"
source "$LIB_DIR/workspace.sh"

main() {
  log "step: stepname"
  
  if isStepDone "STEPNAME" && [[ "${FORCE:-0}" != "1" ]]; then
    log "already done"
    return 0
  fi
  
  # Do work here
  
  markStepDone "STEPNAME"
  log "done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
```

3. Add to `ALL_STEPS` array in `runpodBootstrap.sh`
4. Document in `--list` output

### Adding a New Library Function

1. Add to appropriate `lib/*.sh` file
2. Keep functions idempotent where possible
3. Use `run` wrapper for dry-run support
4. Use `log`/`warn`/`error` for output

## Troubleshooting

### Check logs

```bash
ls -lrt /workspace/runpodTools/logs/
tail -f /workspace/runpodTools/logs/bootstrap.LATEST.log
```

### Check state

```bash
cat /workspace/runpodTools/state.env
```

### Reset state

```bash
rm /workspace/runpodTools/state.env
```

### Dry run

```bash
./runpodFromSSH.sh --dry-run ssh root@HOST -p PORT -i KEY
```

This shows all commands that would be executed without actually running them.
