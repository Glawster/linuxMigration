# RunPod – Quick Ops (this repo)

This file is intended to be uploaded to the pod as `/workspace/help.md` so you can quickly remember:
- what to run
- what ports to expect
- where logs are
- how to diagnose common failures

**Logs live in:** `/workspace/logs` (not `/workspace/logs`)

---

## 1) Start order

### A) Upload models/workflows/help (run locally)

```bash
./uploadModels.sh ssh root@<POD_IP> -p <SSH_PORT> -i ~/.ssh/id_ed25519
```

This script will also try to upload `help.md` (by default it looks next to `uploadModels.sh`).

Remote locations:
- models → `/workspace/ComfyUI/models/...`
- workflows → `/workspace/workflows`
- help → `/workspace/help.md`

---

### B) Start ComfyUI (run on the pod)

```bash
cd /workspace
./comfyStart.sh
```

- port: `8188`
- tmux session: `comfyui`
- log: `/workspace/logs/comfyui.8188.log`

---

### C) Start LLaVA (optional, run on the pod)

```bash
cd /workspace
./llavaStart.sh
```

Defaults (can override via env):
- `LLAVA_MODEL_PATH=liuhaotian/llava-v1.5-7b`
- controller `7001`, worker `7002`, web `7003`

tmux sessions:
- `llava_controller`
- `llava_worker`
- `llava_web`

logs:
- `/workspace/logs/llava.controller.7001.log`
- `/workspace/logs/llava.worker.7002.log`
- `/workspace/logs/llava.web.7003.log`

---

### D) Start the API adapter (optional, run on the pod)

```bash
cd /workspace
./adapterStart.sh
```

- port: `9188`
- tmux session: `llava_adapter`
- log: `/workspace/logs/llava.adapter.9188.log`

Adapter environment variables:
- `LLAVA_GRADIO_URL=http://127.0.0.1:7003`
- `LLAVA_API_NAME=/add_text_1`
- `LLAVA_PREPROCESS=Default`

Compatibility (older requested names):
- `LAVA_GRADIO_URL`, `LAVA_API_NAME` are also accepted.

---

## 2) Check if services are running

### Ports

```bash
ss -lntp
```

Expected:
- `8188` (ComfyUI)
- `7001/7002/7003` (LLaVA)
- `9188` (adapter)

### tmux

```bash
tmux ls
tmux attach -t comfyui
# detach: Ctrl-b then d
```

### Logs

```bash
ls -la /workspace/logs
tail -n 120 /workspace/logs/comfyui.8188.log
```

---

## 3) Health checks

### ComfyUI

```bash
curl -sS http://127.0.0.1:8188/ | head
```

### LLaVA web

```bash
curl -sS http://127.0.0.1:7003/ | head
```

### Adapter

```bash
curl -F "file=@image.png" http://127.0.0.1:9188/analyze
```

---

## 4) Kill a process by port number

Example: port **9188**

```bash
ss -lntp | grep :9188
kill <PID>
# force (only if needed):
kill -9 <PID>
```

If it was started via tmux, prefer:

```bash
tmux kill-session -t llava_adapter
```

---
