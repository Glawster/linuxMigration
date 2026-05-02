#!/usr/bin/env bash
# steps/65_video_upscale.sh
# Install video upscaling tools

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="$(dirname "$SCRIPT_DIR")/lib"

# shellcheck disable=SC1091
source "$LIB_DIR/ssh.sh"
buildSshOpts
# shellcheck disable=SC1091
source "$LIB_DIR/common.sh"
# shellcheck disable=SC1091
source "$LIB_DIR/workspace.sh"

UPSCALE_DIR="${UPSCALE_DIR:-${WORKSPACE_ROOT}/ai-tools/realesrgan-ncnn-vulkan}"
UPSCALE_TMP_DIR="${UPSCALE_TMP_DIR:-${WORKSPACE_ROOT}/tmp/video-upscale}"
UPSCALE_INPUT_DIR="${UPSCALE_INPUT_DIR:-${WORKSPACE_ROOT}/video-input}"
UPSCALE_OUTPUT_DIR="${UPSCALE_OUTPUT_DIR:-${WORKSPACE_ROOT}/video-output}"
UPSCALE_SCRIPT="${UPSCALE_SCRIPT:-${WORKSPACE_ROOT}/videoUpscale.sh}"
REALESRGAN_ZIP_URL="${REALESRGAN_ZIP_URL:-https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases/download/v0.2.0/realesrgan-ncnn-vulkan-20220424-linux.zip}"

ensureUpscalePackages() {
  log "ensuring video upscale system packages"

  if ! runSh "command -v apt-get >/dev/null 2>&1"; then
    warn "apt-get not found. Assuming image already has ffmpeg/wget/unzip."
    return 0
  fi

  runSh "export DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC LANG=C.UTF-8 LC_ALL=C.UTF-8; apt-get update; apt-get install -y ca-certificates ffmpeg unzip wget"
}

installRealEsrgan() {
  if isStepDone "VIDEO_UPSCALE_REALESRGAN" && [[ "${FORCE:-0}" != "1" ]]; then
    log "real-esrgan ncnn vulkan already installed"
    return 0
  fi

  log "installing real-esrgan ncnn vulkan"

  runSh "set -euo pipefail
mkdir -p '${UPSCALE_DIR}'
cd '${UPSCALE_DIR}'
if [[ ! -x ./realesrgan-ncnn-vulkan || '${FORCE:-0}' == '1' ]]; then
  rm -rf realesrgan-ncnn-vulkan-* *.zip
  wget -q '${REALESRGAN_ZIP_URL}' -O realesrgan-ncnn-vulkan-linux.zip
  unzip -q realesrgan-ncnn-vulkan-linux.zip
  rm -f realesrgan-ncnn-vulkan-linux.zip
  chmod +x ./realesrgan-ncnn-vulkan
fi
./realesrgan-ncnn-vulkan -h >/dev/null 2>&1 || true"

  markStepDone "VIDEO_UPSCALE_REALESRGAN"
}

installVideoUpscaleScript() {
  log "installing videoUpscale.sh helper"

  runSh "cat > '${UPSCALE_SCRIPT}' <<'REMOTE_EOF'
#!/usr/bin/env bash
# videoUpscale.sh
# Upscale video by extracting frames, running Real-ESRGAN, then rebuilding with audio.

set -euo pipefail

WORKSPACE_ROOT=\"\${WORKSPACE_ROOT:-/workspace}\"
UPSCALE_DIR=\"\${UPSCALE_DIR:-\${WORKSPACE_ROOT}/ai-tools/realesrgan-ncnn-vulkan}\"
TMP_ROOT=\"\${UPSCALE_TMP_DIR:-\${WORKSPACE_ROOT}/tmp/video-upscale}\"
SCALE=\"\${SCALE:-2}\"
MODEL=\"\${MODEL:-realesrgan-x4plus}\"
FPS=\"\${FPS:-}\"
CRF=\"\${CRF:-18}\"
PRESET=\"\${PRESET:-slow}\"
KEEP_FRAMES=\"\${KEEP_FRAMES:-0}\"

usage() {
  cat <<USAGE
Usage:
  videoUpscale.sh input.mp4 output.mp4 [scale] [model]

Examples:
  videoUpscale.sh /workspace/video-input/source.mp4 /workspace/video-output/source_1080p.mp4 2 realesrgan-x4plus
  MODEL=realesr-animevideov3 CRF=20 videoUpscale.sh input.mp4 output.mp4 2

Environment:
  SCALE       Default scale when arg 3 is omitted. Default: 2
  MODEL       Real-ESRGAN model. Default: realesrgan-x4plus
  FPS         Optional output FPS. If omitted, ffmpeg preserves source timing during extraction/rebuild as closely as possible.
  CRF         x264 quality. Lower is better/larger. Default: 18
  PRESET      x264 preset. Default: slow
  KEEP_FRAMES Keep temporary frames if set to 1. Default: 0
USAGE
}

INPUT=\"\${1:-}\"
OUTPUT=\"\${2:-}\"
SCALE=\"\${3:-\${SCALE}}\"
MODEL=\"\${4:-\${MODEL}}\"

if [[ -z \"$INPUT\" || -z \"$OUTPUT\" ]]; then
  usage >&2
  exit 2
fi

if [[ ! -f \"$INPUT\" ]]; then
  echo \"ERROR: input video not found: $INPUT\" >&2
  exit 1
fi

if [[ ! -x \"$UPSCALE_DIR/realesrgan-ncnn-vulkan\" ]]; then
  echo \"ERROR: realesrgan-ncnn-vulkan not found: $UPSCALE_DIR/realesrgan-ncnn-vulkan\" >&2
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo \"ERROR: ffmpeg not found\" >&2
  exit 1
fi

BASENAME=\"$(basename \"$INPUT\")\"
JOB_ID=\"\${BASENAME%.*}.$(date +%Y%m%d_%H%M%S)\"
JOB_DIR=\"$TMP_ROOT/$JOB_ID\"
FRAMES_DIR=\"$JOB_DIR/frames\"
UPSCALED_DIR=\"$JOB_DIR/upscaled\"
AUDIO_FILE=\"$JOB_DIR/audio.m4a\"

mkdir -p \"$FRAMES_DIR\" \"$UPSCALED_DIR\" \"$(dirname \"$OUTPUT\")\"

cleanup() {
  if [[ \"$KEEP_FRAMES\" != \"1\" ]]; then
    rm -rf \"$JOB_DIR\"
  else
    echo \"kept frames at: $JOB_DIR\"
  fi
}
trap cleanup EXIT

echo \"...extracting frames\"
if [[ -n \"$FPS\" ]]; then
  ffmpeg -hide_banner -y -i \"$INPUT\" -vf \"fps=$FPS\" \"$FRAMES_DIR/frame_%08d.png\"
else
  ffmpeg -hide_banner -y -i \"$INPUT\" \"$FRAMES_DIR/frame_%08d.png\"
fi

echo \"...extracting audio if present\"
ffmpeg -hide_banner -y -i \"$INPUT\" -vn -c:a copy \"$AUDIO_FILE\" >/dev/null 2>&1 || true

echo \"...upscaling frames: scale=$SCALE model=$MODEL\"
\"$UPSCALE_DIR/realesrgan-ncnn-vulkan\" \\
  -i \"$FRAMES_DIR\" \\
  -o \"$UPSCALED_DIR\" \\
  -s \"$SCALE\" \\
  -n \"$MODEL\"

echo \"...rebuilding video\"
if [[ -f \"$AUDIO_FILE\" ]]; then
  ffmpeg -hide_banner -y \\
    -framerate \"\${FPS:-30}\" -i \"$UPSCALED_DIR/frame_%08d.png\" \\
    -i \"$AUDIO_FILE\" \\
    -c:v libx264 -preset \"$PRESET\" -crf \"$CRF\" -pix_fmt yuv420p \\
    -c:a copy -shortest \"$OUTPUT\"
else
  ffmpeg -hide_banner -y \\
    -framerate \"\${FPS:-30}\" -i \"$UPSCALED_DIR/frame_%08d.png\" \\
    -c:v libx264 -preset \"$PRESET\" -crf \"$CRF\" -pix_fmt yuv420p \\
    \"$OUTPUT\"
fi

echo \"upscale complete: $OUTPUT\"
REMOTE_EOF
chmod +x '${UPSCALE_SCRIPT}'"
}

main() {
  if isStepDone "VIDEO_UPSCALE" && [[ "${FORCE:-0}" != "1" ]]; then
    log "video upscale tools already configured (use --force to rerun)"
    return 0
  fi

  runSh "mkdir -p '${UPSCALE_INPUT_DIR}' '${UPSCALE_OUTPUT_DIR}' '${UPSCALE_TMP_DIR}'"

  ensureUpscalePackages
  installRealEsrgan
  installVideoUpscaleScript

  if ! isStepDone "VIDEO_UPSCALE_GPU_CHECK" || [[ "${FORCE:-0}" == "1" ]]; then
    log "checking gpu for video upscale"
    runSh "nvidia-smi || true; vulkaninfo --summary 2>/dev/null || true"
    markStepDone "VIDEO_UPSCALE_GPU_CHECK"
  else
    log "video upscale gpu already checked"
  fi

  markStepDone "VIDEO_UPSCALE"
  log "done"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
