# Quick Reference Card

## Basic Usage

```bash
# From local machine, run everything
./runpodFromSSH.sh ssh root@HOST -p PORT -i ~/.ssh/KEY

# With Kohya enabled
./runpodFromSSH.sh --kohya ssh root@HOST -p PORT -i KEY
```

## Step Control

```bash
# List available steps
./runpodFromSSH.sh --list ssh root@HOST -p PORT -i KEY

# Run only one step
./runpodFromSSH.sh --only 40_comfyui ssh root@HOST -p PORT -i KEY

# Start from a step
./runpodFromSSH.sh --from 30_conda ssh root@HOST -p PORT -i KEY

# Skip a step
./runpodFromSSH.sh --skip 20_base_tools ssh root@HOST -p PORT -i KEY

# Force rerun (ignore state)
./runpodFromSSH.sh --force ssh root@HOST -p PORT -i KEY
```

## Available Steps

1. `10_diagnostics` - System diagnostics
2. `20_base_tools` - Install apt packages
3. `30_conda` - Setup miniconda
4. `40_comfyui` - Setup ComfyUI (optional, default on)
5. `50_kohya` - Setup Kohya SS (optional, default off)
6. `60_upload_models` - Model upload instructions

## Debugging

```bash
# Dry run (show what would happen)
./runpodFromSSH.sh --dry-run ssh root@HOST -p PORT -i KEY

# On remote pod: check logs
tail -100 /workspace/runpodTools/logs/bootstrap.*.log

# On remote pod: check state
cat /workspace/runpodTools/state.env

# On remote pod: run single step
bash /workspace/runpodTools/steps/40_comfyui.sh

# Reset state
rm /workspace/runpodTools/state.env
```

## Common Scenarios

### First Time Setup
```bash
./runpodFromSSH.sh ssh root@HOST -p PORT -i KEY
```

### Add Kohya to Existing Setup
```bash
./runpodFromSSH.sh --only 50_kohya ssh root@HOST -p PORT -i KEY
```

### Fix ComfyUI Without Reinstalling Everything
```bash
./runpodFromSSH.sh --only 40_comfyui --force ssh root@HOST -p PORT -i KEY
```

### Copy Files Without Running
```bash
./runpodFromSSH.sh --no-run ssh root@HOST -p PORT -i KEY
# Then on remote:
bash /workspace/runpodTools/runpodBootstrap.sh
```

### Upload Models
```bash
# Generate script
./generateUploadScript.sh ./uploadModels.sh

# Upload
./uploadModels.sh ssh root@HOST -p PORT -i KEY
```

### Start ComfyUI
```bash
# On remote pod:
bash /workspace/runpodTools/startComfyUI.sh 8188
tmux attach -t comfyui
```

## Files & Locations

| Location | Purpose |
|----------|---------|
| `/workspace/runpodTools/` | Main directory (remote) |
| `/workspace/runpodTools/lib/` | Library functions |
| `/workspace/runpodTools/steps/` | Step scripts |
| `/workspace/runpodTools/logs/` | Timestamped logs |
| `/workspace/runpodTools/state.env` | Completion tracking |
| `/workspace/ComfyUI/` | ComfyUI installation |
| `/workspace/kohya_ss/` | Kohya SS installation |
| `/workspace/miniconda3/` | Miniconda installation |

## Useful Commands

```bash
# Show workspace inventory
bash /workspace/runpodTools/lib/workspace.sh

# Check connectivity
ssh -p PORT -i KEY root@HOST "echo connected"

# View recent logs
ls -lrt /workspace/runpodTools/logs/

# Kill ComfyUI
tmux kill-session -t comfyui

# Manual conda activation
source /workspace/miniconda3/etc/profile.d/conda.sh
conda activate runpod
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Step already done" | Use `--force` to rerun |
| SSH connection fails | Check port, host, and key |
| Need to rerun specific step | Use `--only STEP` |
| Want to see what will happen | Use `--dry-run` |
| Step failed | Check logs in `/workspace/runpodTools/logs/` |
| Reset everything | `rm /workspace/runpodTools/state.env` |

## All Options

### runpodFromSSH.sh (Local)
```
--kohya          Enable Kohya SS
--no-comfyui     Disable ComfyUI
--no-run         Copy files only
--dry-run        Show actions
--force          Force rerun
--from STEP      Start from step
--only STEP      Run one step
--skip STEP      Skip step
--list           List steps
```

### runpodBootstrap.sh (Remote)
```
--comfyui        Enable ComfyUI (default)
--no-comfyui     Disable ComfyUI
--kohya          Enable Kohya
--dry-run        Print only
--force          Ignore state
--from STEP      Start from
--only STEP      Run only
--skip STEP      Skip
--list           List steps
```

## Help

```bash
# Show help
./runpodFromSSH.sh --help
bash /workspace/runpodTools/runpodBootstrap.sh --help

# Read documentation
cat bin/runpod/README.md
cat kohyaTools/MIGRATION.md
```
