# ComfyUI Setup Optimization

## Overview

The `40_comfyui.sh` script has been optimized to support incremental re-runs by breaking down the installation process into granular sub-steps, each tracked independently using `isStepDone` and `markStepDone`.

## Problem

Previously, when re-running the ComfyUI setup step:
- The entire step would be skipped if `DONE_COMFYUI=1` was set
- OR the entire step would re-run from scratch if forced or incomplete
- No way to resume from a partially completed installation
- Long-running pip installations would repeat unnecessarily

## Solution

The script now tracks 6 independent sub-steps:

### 1. `COMFYUI_REPO`
- Clones/updates the main ComfyUI repository
- Skipped if repository already exists and is up-to-date

### 2. `COMFYUI_MANAGER`
- Clones/updates the ComfyUI-Manager custom node
- Skipped if already cloned and up-to-date

### 3. `COMFYUI_PIP_UPGRADE`
- Upgrades pip and wheel in the conda environment
- Skipped if already upgraded in a previous run

### 4. `COMFYUI_REQUIREMENTS`
- Installs packages from ComfyUI's requirements.txt
- Skipped if already installed
- **Major time saver**: PyTorch and other large dependencies won't reinstall

### 5. `COMFYUI_MANAGER_REQUIREMENTS`
- Installs packages from ComfyUI-Manager's requirements.txt
- Skipped if already installed

### 6. `COMFYUI_CUDA_CHECK`
- Verifies CUDA/PyTorch GPU availability
- Quick verification step
- Skipped if already verified successfully

### Always Run
- **comfyStart.sh generation and upload**: Always regenerates to capture any configuration changes

## Benefits

### Time Savings
- **First run**: No change in duration (all sub-steps execute)
- **Re-runs after failure**: Only incomplete sub-steps execute
- **Re-runs after updates**: Only affected sub-steps execute
- **Estimated savings**: 5-15 minutes on typical re-runs

### Improved Reliability
- If pip install fails, you can fix the issue and re-run without repeating git clones
- If network fails during requirements installation, resume from that point
- Better granularity for debugging which sub-step failed

### Better User Feedback
- Clear logging messages indicate which sub-steps are being skipped
- Example output:
  ```
  ...comfyui repository already cloned
  ...comfyui-manager already cloned
  ...pip and wheel already upgraded
  ...installing comfyui requirements
  ```

## Usage

### Normal Run
```bash
./runpodFromSSH.sh ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```
- Skips completed sub-steps automatically

### Force Complete Re-run
```bash
./runpodFromSSH.sh --force ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```
- Forces all sub-steps to re-execute

### Force Specific Sub-step Re-run
If you need to re-run just the requirements installation:
```bash
# SSH into the pod
ssh root@HOST -p PORT -i ~/.ssh/id_ed25519

# Edit state file to remove the specific step marker
cd /workspace/runpodTools
sed -i '/DONE_COMFYUI_REQUIREMENTS=1/d' state.env

# Re-run the step
./runpodBootstrap.sh --only 40_comfyui
```

## State Tracking

The state file at `/workspace/runpodTools/state.env` now tracks:
```bash
DONE_COMFYUI_REPO=1
DONE_COMFYUI_MANAGER=1
DONE_COMFYUI_PIP_UPGRADE=1
DONE_COMFYUI_REQUIREMENTS=1
DONE_COMFYUI_MANAGER_REQUIREMENTS=1
DONE_COMFYUI_CUDA_CHECK=1
DONE_COMFYUI=1
```

## Implementation Pattern

This optimization follows the same pattern used in `30_conda.sh`:

```bash
if ! isStepDone "SUB_STEP_NAME"; then
  log "performing sub-step action"
  # ... do work ...
  markStepDone "SUB_STEP_NAME"
else
  log "sub-step already completed"
fi
```

## Future Enhancements

Potential improvements for consideration:
- Add timestamp tracking to show when each sub-step completed
- Add checksums to detect if requirements.txt changed and trigger re-install
- Add option to embed pod IP/port in state.env for multi-pod workflows (currently not implemented as pods are typically single-use)
