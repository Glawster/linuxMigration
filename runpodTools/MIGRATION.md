# Migration Guide: Old to Modular RunPod Scripts

## Overview

The runpod scripts have been modularized to improve maintainability, idempotency, and debugging capabilities.

## What Changed

### Old Structure
```
kohyaTools/
  runpodFromSSH.sh       (2000 lines, monolithic)
  runpodBootstrap.sh     (25000 lines, monolithic)
```

### New Structure
```
runpodTools/
  lib/                 (reusable libraries)
  steps/               (modular step scripts)
  runpodBootstrap.sh   (step runner)
  runpodFromSSH.sh     (local orchestrator)
```

## Quick Migration

### If you were using:

```bash
./kohyaTools/runpodFromSSH.sh ssh root@host -p 40023 -i ~/.ssh/key
```

### Now use:

```bash
./runpodTools/runpodFromSSH.sh ssh root@host -p 40023 -i ~/.ssh/key
```

## New Features

### 1. Step Control

```bash
# List available steps
./runpodFromSSH.sh --list ssh root@host -p PORT -i KEY

# Run only specific step
./runpodFromSSH.sh --only 40_comfyui ssh root@host -p PORT -i KEY

# Start from specific step
./runpodFromSSH.sh --from 30_conda ssh root@host -p PORT -i KEY

# Skip steps
./runpodFromSSH.sh --skip 20_base_tools ssh root@host -p PORT -i KEY
```

### 2. State Tracking

Steps are tracked in `/workspace/runpodTools/state.env`. Rerunning won't reinstall everything:

```bash
# First run: installs everything
./runpodFromSSH.sh ssh root@host -p PORT -i KEY

# Second run: skips completed steps
./runpodFromSSH.sh ssh root@host -p PORT -i KEY

# Force rerun
./runpodFromSSH.sh --force ssh root@host -p PORT -i KEY
```

### 3. Better Logging

All output is logged to `/workspace/runpodTools/logs/bootstrap.TIMESTAMP.log`:

```bash
# On remote pod:
ls -lrt /workspace/runpodTools/logs/
tail -f /workspace/runpodTools/logs/bootstrap.*.log
```

### 4. Dry Run

See what would happen without making changes:

```bash
./runpodFromSSH.sh --dry-run ssh root@host -p PORT -i KEY
```

## Command Equivalents

| Old Command | New Command |
|------------|-------------|
| `runpodFromSSH.sh ssh ...` | `runpod/runpodFromSSH.sh ssh ...` |
| `runpodFromSSH.sh --kohya ssh ...` | `runpod/runpodFromSSH.sh --kohya ssh ...` |
| `runpodFromSSH.sh --no-comfyui ssh ...` | `runpod/runpodFromSSH.sh --no-comfyui ssh ...` |
| `runpodFromSSH.sh --dry-run ssh ...` | `runpod/runpodFromSSH.sh --dry-run ssh ...` |
| `runpodBootstrap.sh --upload` | `runpod/generateUploadScript.sh` |

## All Options

### Local Side (runpodFromSSH.sh)

```
--kohya          Enable kohya setup
--no-comfyui     Disable comfyui setup
--no-run         Only copy files, don't execute
--dry-run        Show what would happen
--force          Force rerun of all steps
--from STEP      Start from specific step
--only STEP      Run only specific step
--skip STEP      Skip specific step
--list           List available steps
```

### Remote Side (runpodBootstrap.sh)

```
--comfyui        Enable ComfyUI (default on)
--no-comfyui     Disable ComfyUI
--kohya          Enable Kohya (default off)
--dry-run        Print actions only
--force          Ignore state, rerun all
--from STEP      Start from step
--only STEP      Run only step
--skip STEP      Skip step
--list           List steps
```

## Available Steps

1. **10_diagnostics** - System diagnostics
2. **20_base_tools** - Install apt packages
3. **30_conda** - Setup miniconda
4. **40_comfyui** - Setup ComfyUI (optional)
5. **50_kohya** - Setup Kohya SS (optional)
6. **60_upload_models** - Show upload instructions

## Troubleshooting

### Reset State

```bash
# On remote pod:
rm /workspace/runpodTools/state.env
bash /workspace/runpodTools/runpodBootstrap.sh
```

### Check Logs

```bash
# On remote pod:
tail -100 /workspace/runpodTools/logs/bootstrap.*.log
```

### Manual Step Execution

```bash
# On remote pod:
bash /workspace/runpodTools/steps/40_comfyui.sh
```

## Benefits of New Structure

1. **Idempotent**: Safe to rerun, won't reinstall existing components
2. **Modular**: Each step is independent
3. **Debuggable**: Run specific steps, skip others
4. **Logged**: All output saved to files
5. **Testable**: Steps can be tested individually
6. **Maintainable**: Changes isolated to specific files

## Need Help?

See `bin/runpod/README.md` for full documentation.
