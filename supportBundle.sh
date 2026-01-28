#!/usr/bin/env bash
# supportBundle.sh
# Deterministic support bundle for debugging (multi-project).
#
# Run from your "code root" (e.g. ~/bin) and optionally include subfolders:
#   ./supportBundle.sh
#   ./supportBundle.sh --code runpodTools kohyaTools
#
# Output:
#   ./support.YYYYMMDD-N.zip   (created in the current working directory)

set -euo pipefail

# ------------------------------------------------------------
# Args
# ------------------------------------------------------------
CODE_ROOT="$(pwd)"
PROJECTS=()

usage() {
  cat <<EOF
usage:
  $0
  $0 --code <folder1> <folder2> ...

notes:
  - run from the code root (PWD)
  - with no args, bundles the current folder only
  - with --code, bundles the listed subfolders under PWD
EOF
}

if [[ $# -gt 0 ]]; then
  case "${1:-}" in
    --code)
      shift
      # All remaining args are treated as project folders.
      # If none supplied, we fall back to bundling PWD.
      while [[ $# -gt 0 ]]; do
        case "$1" in
          -h|--help) usage; exit 0 ;;
          --*) echo "ERROR: unknown option: $1" >&2; usage; exit 1 ;;
          *) PROJECTS+=("$1"); shift ;;
        esac
      done
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
fi

# Default: bundle current folder only
if [[ ${#PROJECTS[@]} -eq 0 ]]; then
  PROJECTS=(".")
fi

# ------------------------------------------------------------
# Preconditions
# ------------------------------------------------------------
if ! command -v zip >/dev/null 2>&1; then
  echo "ERROR: zip not found on PATH" >&2
  exit 1
fi

# rsync is optional but strongly preferred
HAS_RSYNC="0"
if command -v rsync >/dev/null 2>&1; then
  HAS_RSYNC="1"
fi

# ------------------------------------------------------------
# Output filename (support.YYYYMMDD-N.zip) in CODE_ROOT
# ------------------------------------------------------------
DATE="$(date +%Y%m%d)"
N=1
while [[ -f "${CODE_ROOT}/support.${DATE}-${N}.zip" ]]; do
  ((N++))
done
ZIP_PATH="${CODE_ROOT}/support.${DATE}-${N}.zip"

# ------------------------------------------------------------
# Temp workspace
# ------------------------------------------------------------
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

mkdir -p "$TMPDIR/projects"

# ------------------------------------------------------------
# Metadata
# ------------------------------------------------------------
{
  echo "code_root: ${CODE_ROOT}"
  echo "date: $(date -Is)"
  echo "host: $(hostname)"
  echo "user: $(whoami)"
  echo
  echo "projects:"
  for p in "${PROJECTS[@]}"; do
    echo "  - ${p}"
  done
} > "$TMPDIR/metadata.txt"

# ------------------------------------------------------------
# Helper: snapshot one project
# ------------------------------------------------------------
snapshotProject() {
  local rel="$1"
  local src="${CODE_ROOT}/${rel}"
  local safeName="${rel//\//_}"
  local out="${TMPDIR}/projects/${safeName}"

  mkdir -p "$out"

  if [[ ! -d "$src" ]]; then
    echo "missing project dir: ${src}" > "${out}/MISSING.txt"
    return 0
  fi

  # Basic inventory
  {
    echo "project: ${rel}"
    echo "path: ${src}"
    echo
    echo "=== top level ==="
    ls -al "$src" || true
    echo
    echo "=== tree (depth 4) ==="
    if command -v tree >/dev/null 2>&1; then
      tree -a -L 4 "$src" || true
    else
      find "$src" -maxdepth 4 -type f || true
    fi
  } > "${out}/inventory.txt"

  # Git snapshot if applicable
  if [[ -d "${src}/.git" ]] && command -v git >/dev/null 2>&1; then
    {
      echo "=== git rev ==="
      git -C "$src" rev-parse --short HEAD || true
      echo
      echo "=== git status ==="
      git -C "$src" status --short || true
      echo
      echo "=== git branch ==="
      git -C "$src" branch --show-current || true
      echo
      echo "=== git log (last 20) ==="
      git -C "$src" log -20 --oneline --decorate || true
    } > "${out}/git.txt"

    git -C "$src" diff --no-color > "${out}/git.diff" || true
  else
    echo "not a git repository (or git not installed)" > "${out}/git.txt"
  fi

  # Copy selected content (avoid huge/noisy dirs)
  mkdir -p "${out}/code"

  # ------------------------------------------------------------
  # External configs
  # ------------------------------------------------------------
  CONFIG_ROOT="${TMPDIR}/configs"
  mkdir -p "${CONFIG_ROOT}/kohya"

  KOHYA_CONFIG="${HOME}/.config/kohya/kohyaConfig.json"

  if [[ -f "${KOHYA_CONFIG}" ]]; then
    cp -a "${KOHYA_CONFIG}" "${CONFIG_ROOT}/kohya/"
  else
    echo "missing: ${KOHYA_CONFIG}" > "${CONFIG_ROOT}/kohya/MISSING.txt"
  fi

  if [[ "$HAS_RSYNC" == "1" ]]; then
    rsync -a \
      --exclude '.git/' \
      --exclude 'logs/' \
      --exclude 'state.env' \
      --exclude '__pycache__/' \
      --exclude '*.pyc' \
      --exclude 'miniconda3/' \
      --exclude 'venv/' \
      --exclude '.venv/' \
      --exclude 'models/' \
      --exclude '**/models/' \
      --exclude 'output/' \
      --exclude '**/output/' \
      --exclude 'input/' \
      --exclude '**/input/' \
      --exclude 'node_modules/' \
      --exclude '**/node_modules/' \
      --include 'lib/***' \
      --include 'steps/***' \
      --include '*.sh' \
      --include '*.md' \
      --include '*.json' \
      --include '*.sh' \
      --include '*.py' \
      --include '*.md' \
      --include '*.json' \
      --include '*.txt' \
      --include '*.toml' \
      --include '*.yml' \
      --include '*.yaml' \
      --include 'requirements*.txt' \
      --include 'pyproject.toml' \
      --exclude '*' \
      "${src}/" "${out}/code/" \
      >/dev/null 2>&1 || true
  else
    # Fallback (more primitive): copy likely files if present
    if [[ -d "${src}/lib" ]]; then cp -a "${src}/lib" "${out}/code/" || true; fi
    if [[ -d "${src}/steps" ]]; then cp -a "${src}/steps" "${out}/code/" || true; fi
    find "$src" -maxdepth 1 -type f \( -name '*.sh' -o -name '*.md' -o -name '*.json' \) \
      -exec cp -a {} "${out}/code/" \; 2>/dev/null || true
  fi
}


# ------------------------------------------------------------
# Collect latest log per project (logs/*.log)
# Copies into TMPDIR/logs (flat) to keep bundle small.
# ------------------------------------------------------------
collectLatestLogs() {
  mkdir -p "${TMPDIR}/logs"

  local rel
  for rel in "${PROJECTS[@]}"; do
    local src="${CODE_ROOT}/${rel}"
    local safeName="${rel//\//_}"

    if [[ ! -d "${src}" ]]; then
      continue
    fi

    # Prefer bootstrap logs if present, otherwise any .log
    local latest=""
    mapfile -t latest < <(ls -t "${src}/logs/bootstrap."*.log 2>/dev/null | head -n 2)

    if [[ ${#latest[@]} -eq 0 ]]; then
      mapfile -t latest < <(ls -t "${src}/logs/"*.log 2>/dev/null | head -n 2)
    fi

    for logFile in "${latest[@]}"; do
      [[ -f "$logFile" ]] || continue
      cp -a "$logFile" "${TMPDIR}/logs/${safeName}__$(basename "$logFile")" 2>/dev/null || true
    done

  done
}


# ------------------------------------------------------------
# Snapshot each project
# ------------------------------------------------------------
for p in "${PROJECTS[@]}"; do
  snapshotProject "$p"
done

collectLatestLogs

# ------------------------------------------------------------
# Create zip in CODE_ROOT
# ------------------------------------------------------------
(
  cd "$TMPDIR"
  zip -qr "$ZIP_PATH" .
)

echo
echo "support bundle created:"
echo "  ${ZIP_PATH}"
echo
