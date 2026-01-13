# KohyaTools Argument Standardization Summary

## Overview
This document summarizes the standardization of argument names and configuration keys across all kohyaTools scripts to ensure consistency and ease of use.

## Standardized Arguments

### Primary Arguments
All scripts that interact with training data and ComfyUI now use these standardized argument names (all lowercase):

| Argument | Purpose | Used By |
|----------|---------|---------|
| `--trainingroot` | Root directory containing training data/styles | trainKohya, createKohyaDirs, migrateKohyaRemoveDate, copyToComfyUI |
| `--comfyin` | ComfyUI input directory | batchImg2ImgComfy, copyToComfyUI |
| `--comfyout` | ComfyUI output directory | batchImg2ImgComfy, copyToComfyUI |
| `--workflows` | ComfyUI workflows directory | batchImg2ImgComfy |

### Configuration Keys
All arguments are stored in `~/.config/kohya/kohyaConfig.json` using flat keys:

```json
{
  "trainingRoot": "/path/to/training/data",
  "comfyIn": "/path/to/ComfyUI/input",
  "comfyOut": "/path/to/ComfyUI/output",
  "workflows": "/path/to/ComfyUI/workflows"
}
```

## Changes Made

### 1. batchImg2ImgComfy.py
**Before:**
- Argument: `--inputDir`
- Config key: `comfyInputDir`

**After:**
- Argument: `--comfyin` (lowercase)
- Argument: `--comfyout` (lowercase)
- Argument: `--workflows` (lowercase, renamed from `--workflowsDir`)
- Config keys: `comfyIn`, `comfyOut`, `workflows`

**Impact:**
- Consistent with copyToComfyUI.py naming
- All arguments in lowercase for consistency
- Both input and output paths now configurable
- Config values automatically saved and reused

### 2. copyToComfyUI.py
**Before:**
- Config structure: Nested `comfyUI.inputDir` and `comfyUI.outputDir`
- Used helper function `getNestedDictValue()` to access nested keys

**After:**
- Config structure: Flat `comfyIn` and `comfyOut` (lowercase keys)
- Arguments: `--comfyin` and `--comfyout` (all lowercase)
- Direct config access with `config.get()`
- Simplified config update logic

**Impact:**
- Consistent with batchImg2ImgComfy.py config structure
- All arguments in lowercase for consistency
- Simpler config management

### 3. Other Scripts
The following scripts already used standardized `--trainingRoot`:
- `trainKohya.py` - ✓ Already compliant
- `createKohyaDirs.py` - ✓ Already compliant
- `migrateKohyaRemoveDate.py` - ✓ Already compliant

All these scripts properly save `trainingRoot` to the config file.

## Benefits

1. **Consistency**: All scripts use the same argument names (all lowercase) for the same purposes
2. **Simplified Configuration**: Flat config structure is easier to understand and manage
3. **Reduced Confusion**: Users can switch between scripts without learning different argument names
4. **Config Reuse**: Set values once, used across all scripts
5. **Better Integration**: Scripts can easily share configuration values
6. **Lowercase Convention**: All arguments follow lowercase naming convention

## Migration Guide

### For Users with Existing Configs

If you have an existing `~/.config/kohya/kohyaConfig.json` with old structure:

**Old format:**
```json
{
  "comfyUI": {
    "inputDir": "/home/user/ComfyUI/input",
    "outputDir": "/home/user/ComfyUI/output"
  }
}
```

**New format:**
```json
{
  "comfyIn": "/home/user/ComfyUI/input",
  "comfyOut": "/home/user/ComfyUI/output",
  "workflows": "/home/user/ComfyUI/workflows"
}
```

**Migration Steps:**
1. Edit `~/.config/kohya/kohyaConfig.json`
2. Move `comfyUI.inputDir` → `comfyIn` (or `comfyInput` → `comfyIn`)
3. Move `comfyUI.outputDir` → `comfyOut` (or `comfyOutput` → `comfyOut`)
4. Rename `comfyWorkflowsDir` → `workflows`
5. Remove the now-empty `comfyUI` object if present
6. Or simply delete the config file and let the scripts recreate it with new values

### For Script Users

**Old command:**
```bash
python batchImg2ImgComfy.py --inputDir ~/ComfyUI/input
# or
python batchImg2ImgComfy.py --comfyInput ~/ComfyUI/input
```

**New command:**
```bash
python batchImg2ImgComfy.py --comfyin ~/ComfyUI/input
python copyToComfyUI.py --comfyin ~/ComfyUI/input --comfyout ~/ComfyUI/output
```

The first time you run with the new argument names, they will be saved to the config file and become the default for future runs.

## Verification

All scripts have been syntax-checked and verified to:
- ✅ Parse arguments correctly (all lowercase)
- ✅ Load config values properly
- ✅ Save config updates (except in --dry-run mode)
- ✅ Use standardized argument names (--comfyin, --comfyout, --workflows, --trainingroot)
- ✅ Use flat config keys

## Related Documentation

- See `EXAMINATION_REPORT.md` for detailed examination of all scripts
- See `kohyaConfig.py` for config management implementation
- Run any script with `--help` to see all available arguments

---
**Last Updated**: 2026-01-12  
**Status**: ✅ Complete - All Scripts Standardized
