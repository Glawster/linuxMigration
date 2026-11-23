#!/usr/bin/env bash
# pdfFiler.sh: launcher for the pdfFiler Python project (ADR 011).
#
#   pdfFiler.sh [-y|--confirm] [--root DIR] [--inbox DIR]   file the inbox
#   pdfFiler.sh suggest PDF...                              show suggestions
#   pdfFiler.sh index show                                  what it has learned
#   pdfFiler.sh --help
#
# Runs from source in a Python that has organiseMyProjects: the active
# python3, then the py312 environment this repository's .envrc uses, so it
# works from a shell where no conda environment is active.
# Guide: documentation/pdfFiler.md
set -euo pipefail

_PDF_FILER_ROOT="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"

for python in "${PDF_FILER_PYTHON:-}" python3 "${CONDA_DIR:-$HOME/miniconda3}/envs/py312/bin/python3"; do
    [[ -n "$python" ]] || continue
    if "$python" -c 'import organiseMyProjects' 2>/dev/null; then
        export PYTHONPATH="$_PDF_FILER_ROOT/pdfFiler/src${PYTHONPATH:+:$PYTHONPATH}"
        exec "$python" -m pdfFiler "$@"
    fi
done

echo "ERROR: no Python with organiseMyProjects found; install it or set PDF_FILER_PYTHON" >&2
exit 1
