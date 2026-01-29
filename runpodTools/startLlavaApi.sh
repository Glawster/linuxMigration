#!/usr/bin/env bash
set -e
source "/workspace/miniconda3/etc/profile.d/conda.sh"
conda activate "llava"
echo "llava env active: $(python -V)"
