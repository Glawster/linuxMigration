# Additional Step Optimizations

## Overview

Following the ComfyUI optimization pattern, granular sub-step tracking has been extended to additional installation steps: LLaVA (70_llava.sh), LLaVA Adapter (75_llava_adapter.sh), and Kohya SS (50_kohya.sh).

## 70_llava.sh Optimization

### Sub-steps Added

1. **LLAVA_REPO** - Clone/update LLaVA repository and checkout specific ref
2. **LLAVA_ENV** - Create conda environment
3. **LLAVA_PIP_UPGRADE** - Upgrade pip, wheel, and setuptools
4. **LLAVA_INSTALL** - Install LLaVA in editable mode
5. **LLAVA_VERIFY** - Verify LLaVA import

### Time Savings

- **First run**: No change in duration (all sub-steps execute)
- **Re-runs after failure**: Only incomplete sub-steps execute
- **Estimated savings**: 3-8 minutes on typical re-runs

### Example Output

```bash
...llava repository already cloned
...llava conda environment already created
...pip, wheel, and setuptools already upgraded
...installing llava (editable)
```

## 75_llava_adapter.sh Optimization

### Sub-steps Added

1. **LLAVA_ADAPTER_DEPS** - Install FastAPI, uvicorn, gradio_client, python-multipart
2. **LLAVA_ADAPTER_START** - Start adapter service in tmux

### Time Savings

- **First run**: No change in duration
- **Re-runs**: Skip dependency installation if already complete
- **Estimated savings**: 1-3 minutes on typical re-runs

### Always Run

- Adapter script generation and upload (always regenerates to capture configuration changes)

## 50_kohya.sh Optimization

### Sub-steps Added

1. **KOHYA_REPO** - Clone/update Kohya SS repository
2. **KOHYA_SUBMODULES** - Initialize and update git submodules
3. **KOHYA_REQUIREMENTS** - Install dependencies from requirements.txt

### Time Savings

- **First run**: No change in duration
- **Re-runs**: Skip completed sub-steps
- **Estimated savings**: 2-5 minutes on typical re-runs (especially submodule operations)

## State Tracking

The state file at `/workspace/runpodTools/state.env` now tracks these additional sub-steps:

```bash
# LLaVA
DONE_LLAVA_REPO=1
DONE_LLAVA_ENV=1
DONE_LLAVA_PIP_UPGRADE=1
DONE_LLAVA_INSTALL=1
DONE_LLAVA_VERIFY=1
DONE_LLAVA=1

# LLaVA Adapter
DONE_LLAVA_ADAPTER_DEPS=1
DONE_LLAVA_ADAPTER_START=1
DONE_LLAVA_ADAPTER=1

# Kohya SS
DONE_KOHYA_REPO=1
DONE_KOHYA_SUBMODULES=1
DONE_KOHYA_REQUIREMENTS=1
DONE_KOHYA=1
```

## Implementation Pattern

All optimizations follow the same idempotent pattern:

```bash
if ! isStepDone "SUB_STEP_NAME"; then
  log "performing action"
  # do work
  markStepDone "SUB_STEP_NAME"
else
  log "already completed"
fi
```

## Usage

### Normal Run
```bash
./runpodFromSSH.sh --llava ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```
- Skips completed sub-steps automatically

### Force Complete Re-run
```bash
./runpodFromSSH.sh --llava --force ssh root@HOST -p PORT -i ~/.ssh/id_ed25519
```
- Forces all sub-steps to re-execute

### Force Specific Sub-step Re-run
```bash
# SSH into the pod
ssh root@HOST -p PORT -i ~/.ssh/id_ed25519

# Edit state file to remove specific step marker
cd /workspace/runpodTools
sed -i '/DONE_LLAVA_INSTALL=1/d' state.env

# Re-run the step
./runpodBootstrap.sh --only 70_llava
```

## Combined Impact

When running all steps (base_tools, conda, comfyui, kohya, llava), the cumulative time savings on re-runs can be:

- **Best case** (all sub-steps already complete): 15-30 minutes
- **Typical case** (some failures mid-step): 10-20 minutes
- **Worst case** (failure at last sub-step): 5-10 minutes

## Quality Assurance

- ✅ Bash syntax validation passed for all files
- ✅ Shellcheck passed with no warnings
- ✅ Pattern consistent with 30_conda.sh and 40_comfyui.sh
- ✅ Removed unused variables for code quality

## Testing Recommendation

While automated validation passed, manual testing on an actual RunPod instance is recommended to verify the optimizations work as expected in the real environment, especially for:

- LLaVA installation and verification
- LLaVA Adapter service startup
- Kohya submodule initialization
