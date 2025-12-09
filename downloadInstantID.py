from huggingface_hub import hf_hub_download

LOCAL_DIR = "InstantID_models"

# 1) antelopev2 face encoder (from MonsterMMORPG/tools)
#    This zip contains the antelopev2 ONNX files in the right structure.
print("Downloading antelopev2.zip ...")
hf_hub_download(
    repo_id="MonsterMMORPG/tools",
    filename="antelopev2.zip",
    local_dir=LOCAL_DIR,
)

# 2) InstantID ip-adapter (main model) from InstantX/InstantID
print("Downloading ip-adapter.bin ...")
hf_hub_download(
    repo_id="InstantX/InstantID",
    filename="ip-adapter.bin",
    local_dir=LOCAL_DIR,
)

# 3) (Optional but recommended) ControlNet model for InstantID
print("Downloading ControlNetModel/diffusion_pytorch_model.safetensors ...")
hf_hub_download(
    repo_id="InstantX/InstantID",
    filename="ControlNetModel/diffusion_pytorch_model.safetensors",
    local_dir=LOCAL_DIR,
)

print("Done. Files saved under:", LOCAL_DIR)

