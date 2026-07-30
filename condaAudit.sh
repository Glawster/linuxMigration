#!/usr/bin/env bash
# Audit Conda environments and preview available package updates.

set -euo pipefail

DRY_PREFIX="${DRY_PREFIX:-[]}"

logInfo() {
    echo "...$*"
}

logWarn() {
    echo "WARNING: $*"
}

boxAdvice() {
    local message="$*"
    local width=72
    local innerWidth=$((width - 2))
    local border

    border="$(printf '%*s' "${width}" '' | tr ' ' '-')"

    echo "+${border}+"

    while IFS= read -r line; do
        printf "| %-*s |
" "${innerWidth}" "${line}"
    done < <(printf '%s
' "${message}" | fold -s -w "${innerWidth}")

    echo "+${border}+"
}

boxAdviceBlock() {
    local width=72
    local innerWidth=$((width - 2))
    local border

    border="$(printf '%*s' "${width}" '' | tr ' ' '-')"

    echo "+${border}+"

    while IFS= read -r line; do
        printf "| %-*s |
" "${innerWidth}" "${line}"
    done < <(fold -s -w "${innerWidth}")

    echo "+${border}+"
}

resolveCondaExe() {
    local candidates=(
        "${CONDA_EXE:-}"
        "${CONDA_DIR:-}/bin/conda"
        "${HOME}/miniconda3/bin/conda"
        "${HOME}/anaconda3/bin/conda"
        "$(command -v conda 2>/dev/null || true)"
    )

    for candidate in "${candidates[@]}"; do
        if [[ -n "${candidate}" && -x "${candidate}" ]]; then
            echo "${candidate}"
            return 0
        fi
    done

    return 1
}

checkEnv() {
    local condaExe="$1"
    local envName="$2"

    echo
    echo "## ${envName}"

    "${condaExe}" run -n "${envName}" python --version 2>/dev/null || {
        logWarn "could not run python in env: ${envName}"
        return
    }

    local packages
    packages="$("${condaExe}" run -n "${envName}" python - <<'PY'
import importlib.metadata as md

names = [
    "numpy",
    "torch",
    "torchvision",
    "transformers",
    "tokenizers",
    "gradio",
    "gradio_client",
    "httpx",
    "accelerate",
    "bitsandbytes",
    "peft",
    "pyside6",
]

for name in names:
    try:
        print(f"{name}=={md.version(name)}")
    except md.PackageNotFoundError:
        pass
PY
)"

    if [[ -z "${packages}" ]]; then
        logInfo "no watched packages found"
    else
        echo "${packages}"
    fi

    if echo "${packages}" | grep -q '^numpy==2'; then
        boxAdvice "WARNING: numpy 2.x detected; older torch/comfyui/llava stacks may need numpy<2"
    fi

    if echo "${packages}" | grep -q '^torch==2\.1\.2'; then
        logInfo "torch 2.1.2 detected; keep torchvision around 0.16.2 for compatibility"
    fi

    if echo "${packages}" | grep -q '^transformers==4\.37\.2'; then
        logInfo "llava-compatible transformers version detected"
    fi

    if echo "${packages}" | grep -q '^gradio==4\.16\.0'; then
        logInfo "llava-compatible gradio version detected"
    fi

    if [[ "${envName}" =~ ^(llava|joycaption|runpod|kohya|comfyui)$ ]]; then
        boxAdvice "WARNING: special env detected; avoid blind 'conda update --all' unless you have a rollback plan"
    fi
}

main() {
    local condaExe

    condaExe="$(resolveCondaExe)" || {
        echo "ERROR: Conda executable not found."
        echo "Try:"
        echo "  source ~/miniconda3/etc/profile.d/conda.sh"
        exit 1
    }

    logInfo "conda exe: ${condaExe}"
    "${condaExe}" --version

    echo
    echo "# conda info"
    "${condaExe}" info | grep -E 'active environment|base environment|conda version|channel URLs|package cache|envs directories' || true

    echo
    echo "# environments"
    "${condaExe}" env list

    echo
    echo "# audit"

    mapfile -t envNames < <("${condaExe}" env list | awk '
        /^[^#[:space:]]/ {
            print $1
        }
    ' | grep -v '^base$' || true)

    checkEnv "${condaExe}" "base"

    for envName in "${envNames[@]}"; do
        checkEnv "${condaExe}" "${envName}"
    done

    echo
    cat <<'EOF' | boxAdviceBlock
Suggested safe commands:

conda update -n base conda
conda update -n base --all --dry-run

# preview a specific env update
conda activate ENV_NAME
conda update --all --dry-run

# fix common ai-stack numpy issue
conda install "numpy<2"

For AI environments (llava, comfyui, kohya, runpod),
avoid blind global updates without a rollback plan.
EOF
}

main "$@"
