# KohyaTools Argument Standardization Summary

## Overview
This document summarizes the standardization of argument names and configuration keys across all kohyaTools scripts to ensure consistency and ease of use.

## Standardized Arguments

### Primary Arguments
All scripts that interact with training data and ComfyUI now use these standardized argument names:

| Argument | Purpose | Used By |
|----------|---------|---------|
| `--trainingRoot` | Root directory containing training data/styles | trainKohya, createKohyaDirs, migrateKohyaRemoveDate, copyToComfyUI |
| `--comfyInput` | ComfyUI input directory | batchImg2ImgComfy, copyToComfyUI |
| `--comfyOutput` | ComfyUI output directory | batchImg2ImgComfy, copyToComfyUI |

### Configuration Keys
All arguments are stored in `~/.config/kohya/kohyaConfig.json` using flat keys:

```json
{
  "trainingRoot": "/path/to/training/data",
  "comfyInput": "/path/to/ComfyUI/input",
  "comfyOutput": "/path/to/ComfyUI/output"
}
```

## Changes Made

### 1. batchImg2ImgComfy.py
**Before:**
- Argument: `--inputDir`
- Config key: `comfyInputDir`

**After:**
- Argument: `--comfyInput`
- Config key: `comfyInput`
- Added: `--comfyOutput` and `comfyOutput` config key

**Impact:**
- Consistent with copyToComfyUI.py naming
- Both input and output paths now configurable
- Config values automatically saved and reused

### 2. copyToComfyUI.py
**Before:**
- Config structure: Nested `comfyUI.inputDir` and `comfyUI.outputDir`
- Used helper function `getNestedDictValue()` to access nested keys

**After:**
- Config structure: Flat `comfyInput` and `comfyOutput`
- Direct config access with `config.get()`
- Simplified config update logic

**Impact:**
- Consistent with batchImg2ImgComfy.py config structure
- Simpler config management
- No breaking changes to argument names (already used `--comfyInput` and `--comfyOutput`)

### 3. Other Scripts
The following scripts already used standardized `--trainingRoot`:
- `trainKohya.py` - ✓ Already compliant
- `createKohyaDirs.py` - ✓ Already compliant
- `migrateKohyaRemoveDate.py` - ✓ Already compliant

All these scripts properly save `trainingRoot` to the config file.

## Benefits

1. **Consistency**: All scripts use the same argument names for the same purposes
2. **Simplified Configuration**: Flat config structure is easier to understand and manage
3. **Reduced Confusion**: Users can switch between scripts without learning different argument names
4. **Config Reuse**: Set values once, used across all scripts
5. **Better Integration**: Scripts can easily share configuration values

## Migration Guide

### For Users with Existing Configs

If you have an existing `~/.config/kohya/kohyaConfig.json` with nested structure:

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
  "comfyOutput": "/home/user/ComfyUI/output"
}
```

**Migration Steps:**
1. Edit `~/.config/kohya/kohyaConfig.json`
2. Move `comfyUI.inputDir` → `comfyInput`
3. Move `comfyUI.outputDir` → `comfyOutput`
4. Remove the now-empty `comfyUI` object
5. Or simply delete the config file and let the scripts recreate it with new values

### For Script Users

**Old command:**
```bash
python batchImg2ImgComfy.py --inputDir ~/ComfyUI/input
```

**New command:**
```bash
python batchImg2ImgComfy.py --comfyInput ~/ComfyUI/input
```

The first time you run with the new argument names, they will be saved to the config file and become the default for future runs.

## Verification

All scripts have been syntax-checked and verified to:
- ✅ Parse arguments correctly
- ✅ Load config values properly
- ✅ Save config updates (except in --dry-run mode)
- ✅ Use standardized argument names
- ✅ Use flat config keys

## Related Documentation

- See `EXAMINATION_REPORT.md` for detailed examination of all scripts
- See `kohyaConfig.py` for config management implementation
- Run any script with `--help` to see all available arguments

---
**Last Updated**: 2026-01-12  
**Status**: ✅ Complete - All Scripts Standardized
