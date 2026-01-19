#!/usr/bin/env bash
# runpod_kohya_setup.sh
# One-click (idempotent-ish) setup for RunPod SSH box: conda + kohya_ss + CUDA PyTorch + sanity checks.
# Run on the POD (after SSH in):  bash runpodKohyaSetup.sh
# ssh root@213.192.2.91 -p 40071 -i ~/.ssh/id_ed25519
# rsync -av --progress -e "ssh -p 40071" /mnt/myVideo/Adult/tumblrForMovie/kathy/ root@213.192.2.91:/root/data/kathy/
# rsync -av --progress -e "ssh -p 40071" /mnt/models/v1-5-pruned-emaonly.safetensors root@213.192.2.91:/root/models/
# in reverse direction:
# rsync -av --progress -e "ssh -p 40071" root@213.192.2.91:/root/data/kathy/output/* /mnt/myVideo/Adult/tumblrForMovie/kathy/output
 
set -euo pipefail

# ---------------------------
# CONFIG (edit if you want)
# ---------------------------
KOHYA_DIR="${KOHYA_DIR:-/root/kohya_ss}"
MINICONDA_DIR="${MINICONDA_DIR:-/root/miniconda3}"
ENV_NAME="${ENV_NAME:-kohya}"
PYTHON_VERSION="${PYTHON_VERSION:-3.10}"
TORCH_CUDA_INDEX_URL="${TORCH_CUDA_INDEX_URL:-https://download.pytorch.org/whl/cu121}"

# Data/model locations on the pod (you rsync into these)
DATA_ROOT="${DATA_ROOT:-/root/data}"
MODELS_ROOT="${MODELS_ROOT:-/root/models}"

# Optional: If you want the script to print a ready-to-run training command at the end
BASE_MODEL_FILENAME="${BASE_MODEL_FILENAME:-v1-5-pruned-emaonly.safetensors}"
STYLE_NAME="${STYLE_NAME:-kathy}"
TRAIN_DIR="${TRAIN_DIR:-${DATA_ROOT}/${STYLE_NAME}}"
OUTPUT_DIR="${OUTPUT_DIR:-${DATA_ROOT}/${STYLE_NAME}/output}"

# Default training knobs (safe on 3090; adjust later)
NETWORK_DIM="${NETWORK_DIM:-16}"
NETWORK_ALPHA="${NETWORK_ALPHA:-16}"
RESOLUTION="${RESOLUTION:-512,512}"
BATCH_SIZE="${BATCH_SIZE:-2}"
EPOCHS="${EPOCHS:-20}"
MAX_BUCKET_RESO="${MAX_BUCKET_RESO:-640}"

# ---------------------------
# Helpers
# ---------------------------
log() { echo -e "\n==> $*\n"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "ERROR: missing command: $1"; exit 1; }
}

# ---------------------------
# 0) Basic checks
# ---------------------------
log "checking gpu availability (nvidia-smi)"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi || true
else
  echo "WARNING: nvidia-smi not found. Are you on a CUDA-enabled RunPod template?"
fi

# ---------------------------
# 1) OS packages
# ---------------------------
log "installing os packages (git, wget, tmux, build tools)"
export DEBIAN_FRONTEND=noninteractive
apt update -y
apt install -y git wget rsync tmux htop unzip build-essential python3-dev ca-certificates

# ---------------------------
# 2) Miniconda install (if needed) + conda init gotcha
# ---------------------------
if [[ ! -x "${MINICONDA_DIR}/bin/conda" ]]; then
  log "installing miniconda to ${MINICONDA_DIR}"
  cd /root
  wget -q https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O /root/Miniconda3-latest-Linux-x86_64.sh
  bash /root/Miniconda3-latest-Linux-x86_64.sh -b -p "${MINICONDA_DIR}"
fi

# Ensure conda on PATH for this script
export PATH="${MINICONDA_DIR}/bin:${PATH}"

# Conda init gotcha: make 'conda activate' work in interactive shells later.
# For this script run, we'll use 'source conda.sh' to activate reliably.
if ! grep -q "conda initialize" /root/.bashrc 2>/dev/null; then
  log "running 'conda init bash' (so future shells can conda activate)"
  "${MINICONDA_DIR}/bin/conda" init bash >/dev/null 2>&1 || true
fi

# Activate conda in this non-login script context
# shellcheck disable=SC1091
source "${MINICONDA_DIR}/etc/profile.d/conda.sh"

# ---------------------------
# 3) Create/activate env
# ---------------------------
log "creating conda env '${ENV_NAME}' (python ${PYTHON_VERSION}) if needed"
if ! conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
  conda create -n "${ENV_NAME}" "python=${PYTHON_VERSION}" -y
fi

log "activating env '${ENV_NAME}'"
conda activate "${ENV_NAME}"
python -V
pip install --upgrade pip

# ---------------------------
# 4) Install CUDA PyTorch
# ---------------------------
log "installing pytorch (cuda) from ${TORCH_CUDA_INDEX_URL}"
pip install -U torch torchvision torchaudio --index-url "${TORCH_CUDA_INDEX_URL}"

log "verifying torch cuda"
python - <<'PY'
import torch
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
else:
    print("WARNING: torch cuda is not available. Check CUDA template/driver.")
PY

# ---------------------------
# 5) Clone kohya_ss + submodules gotcha
# ---------------------------
if [[ ! -d "${KOHYA_DIR}" ]]; then
  log "cloning kohya_ss into ${KOHYA_DIR}"
  git clone https://github.com/bmaltais/kohya_ss.git "${KOHYA_DIR}"
fi

log "updating kohya_ss and initializing submodules (sd-scripts gotcha)"
cd "${KOHYA_DIR}"
git pull --rebase || true
git submodule update --init --recursive

if [[ ! -f "${KOHYA_DIR}/sd-scripts/train_network.py" ]]; then
  echo "ERROR: sd-scripts/train_network.py not found. Submodule init failed."
  exit 1
fi

# ---------------------------
# 6) Install kohya requirements
# ---------------------------
log "installing kohya requirements"
pip install -r requirements.txt

# ---------------------------
# 7) Create standard folders
# ---------------------------
log "creating standard folders"
mkdir -p "${DATA_ROOT}" "${MODELS_ROOT}"

# ---------------------------
# 8) CUDA allocator fragmentation (OOM gotcha)
# ---------------------------
log "setting CUDA allocator env var suggestion"
cat <<'TXT'
Tip (recommended before training to reduce fragmentation OOMs):
  export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
TXT

# ---------------------------
# 9) Print next-step commands (upload + train)
# ---------------------------
log "next steps: upload + train"

cat <<EOF
1) Upload dataset (run this on YOUR LOCAL machine):
   rsync -av --progress -e "ssh -p <PORT>" \\
     /path/to/${STYLE_NAME}/ \\
     root@<IP>:${TRAIN_DIR}/

2) Upload base model (run on YOUR LOCAL machine):
   rsync -av --progress -e "ssh -p <PORT>" \\
     /path/to/${BASE_MODEL_FILENAME} \\
     root@<IP>:${MODELS_ROOT}/

3) Verify on the pod:
   ls ${TRAIN_DIR}/10_${STYLE_NAME} | head
   ls -lh ${MODELS_ROOT}/${BASE_MODEL_FILENAME}

4) Run training (on the pod; use tmux):
   tmux new -s kohya

   export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
   cd ${KOHYA_DIR}
   conda activate ${ENV_NAME}

   accelerate launch sd-scripts/train_network.py \\
     --pretrained_model_name_or_path=${MODELS_ROOT}/${BASE_MODEL_FILENAME} \\
     --train_data_dir=${TRAIN_DIR} \\
     --output_dir=${OUTPUT_DIR} \\
     --output_name=${STYLE_NAME}_person_r${NETWORK_DIM}_${RESOLUTION//,/x}_bs${BATCH_SIZE} \\
     --caption_extension=.txt \\
     --resolution=${RESOLUTION} \\
     --network_module=networks.lora \\
     --network_dim=${NETWORK_DIM} \\
     --network_alpha=${NETWORK_ALPHA} \\
     --train_batch_size=${BATCH_SIZE} \\
     --gradient_accumulation_steps=1 \\
     --max_train_epochs=${EPOCHS} \\
     --learning_rate=8e-5 \\
     --text_encoder_lr=5e-5 \\
     --unet_lr=8e-5 \\
     --optimizer_type=AdamW \\
     --lr_scheduler=cosine \\
     --lr_warmup_steps=50 \\
     --mixed_precision=fp16 \\
     --save_every_n_epochs=1 \\
     --save_model_as=safetensors \\
     --clip_skip=2 \\
     --enable_bucket \\
     --min_bucket_reso=320 \\
     --max_bucket_reso=${MAX_BUCKET_RESO} \\
     --bucket_reso_steps=64

If you OOM:
- drop --train_batch_size to 1, OR
- keep batch 1 and set --gradient_accumulation_steps=4, OR
- reduce --max_bucket_reso further (e.g. 576)
EOF

log "setup complete"
