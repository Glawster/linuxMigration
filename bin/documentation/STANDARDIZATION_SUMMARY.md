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
All arguments are stored in `~/.config/kohya/kohyaConfig.json` using flat keys (config keys use camelCase, not shortened forms):

```json
{
  "trainingRoot": "/path/to/training/data",
  "comfyInput": "/path/to/ComfyUI/input",
  "comfyOutput": "/path/to/ComfyUI/output",
  "comfyWorkflowsDir": "/path/to/ComfyUI/workflows"
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
- Config keys: `comfyInput`, `comfyOutput`, `comfyWorkflowsDir` (unchanged camelCase)

**Impact:**
- Consistent with copyToComfyUI.py naming
- All CLI arguments in lowercase for simpler user experience
- Config keys remain in camelCase for internal consistency
- Both input and output paths now configurable
- Config values automatically saved and reused

### 2. copyToComfyUI.py
**Before:**
- Config structure: Nested `comfyUI.inputDir` and `comfyUI.outputDir`
- Used helper function `getNestedDictValue()` to access nested keys

**After:**
- Config structure: Flat `comfyInput` and `comfyOutput` (camelCase keys)
- Arguments: `--comfyin` and `--comfyout` (all lowercase)
- Direct config access with `config.get()`
- Simplified config update logic

**Impact:**
- Consistent with batchImg2ImgComfy.py config structure
- All CLI arguments in lowercase for simpler user experience
- Config keys remain in camelCase for internal consistency
- Simpler config management

### 3. Other Scripts
The following scripts already used standardized `--trainingRoot`:
- `trainKohya.py` - ✓ Already compliant
- `createKohyaDirs.py` - ✓ Already compliant
- `migrateKohyaRemoveDate.py` - ✓ Already compliant

All these scripts properly save `trainingRoot` to the config file.

## Benefits

1. **Consistency**: All scripts use the same argument names (all lowercase) for the same purposes
2. **Simplified Configuration**: Flat config structure with camelCase keys is easier to understand and manage
3. **Reduced Confusion**: Users can switch between scripts without learning different argument names
4. **Config Reuse**: Set values once, used across all scripts
5. **Better Integration**: Scripts can easily share configuration values
6. **User-Friendly CLI**: All CLI arguments follow lowercase naming convention for ease of use
7. **Internal Consistency**: Config keys maintain camelCase for programmatic consistency

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
  "comfyInput": "/home/user/ComfyUI/input",
  "comfyOutput": "/home/user/ComfyUI/output",
  "comfyWorkflowsDir": "/home/user/ComfyUI/workflows"
}
```

**Migration Steps:**
1. Edit `~/.config/kohya/kohyaConfig.json`
2. Move `comfyUI.inputDir` → `comfyInput` (flat structure, camelCase)
3. Move `comfyUI.outputDir` → `comfyOutput` (flat structure, camelCase)
4. Keep `comfyWorkflowsDir` as is (already in correct format)
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
- ✅ Parse CLI arguments correctly (all lowercase for user simplicity)
- ✅ Load config values properly (camelCase keys internally)
- ✅ Save config updates (except in --dry-run mode)
- ✅ Use standardized argument names (--comfyin, --comfyout, --workflows, --trainingroot)
- ✅ Use flat config keys (comfyInput, comfyOutput, comfyWorkflowsDir)

## Related Documentation

- See `EXAMINATION_REPORT.md` for detailed examination of all scripts
- See `kohyaConfig.py` for config management implementation
- Run any script with `--help` to see all available arguments

---
**Last Updated**: 2026-01-12  
**Status**: ✅ Complete - All Scripts Standardized
