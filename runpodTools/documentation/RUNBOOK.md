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

# LLaVA Installation Smoke Test

This document describes the **end‑to‑end smoke test** used to validate a LLaVA deployment (controller, worker, and adapter) on **RunPod** as well as from a **local machine** via the RunPod proxy.

The test is implemented as a single shell script:

```
testLlavaInstall.sh
```

It is intentionally **non‑destructive**: it only performs read‑only HTTP requests and one inference call.

---

## What the test validates

### On the pod

When the script detects `/workspace`, it assumes it is running **inside the pod** and checks:

1. **Ports are listening**

   * 7001 – controller
   * 7002 – worker
   * 7003 – gradio web (optional)
   * 9188 – adapter

2. **Controller API**

   * `POST /list_models`
   * `POST /get_worker_address`

3. **Worker API**

   * `POST /worker_generate`
   * fallback to `POST /worker_generate_stream`

4. **Adapter API**

   * `POST /analyze` using multipart image upload

### On a local machine

When `/workspace` is not present, the script assumes **local execution** and:

* Tests the adapter **via RunPod proxy**
* Does **not** attempt to access controller or worker unless you explicitly expose them

---

## Image handling

* On the pod:

  * If `--img` is **not supplied**, the script automatically selects the **first `*.png`** found in `/workspace`.
* On local:

  * You must provide `--img` with a local file path.

---

## Usage

### Pod (automatic image selection)

```
./testLlavaInstall.sh
```

### Pod (explicit image)

```
./testLlavaInstall.sh --img /workspace/bp-13.png
```

### Local machine (build adapter URL from PODID)

```
./testLlavaInstall.sh \
  --podid mcswsnfzk7f1h5 \
  --img /home/andy/.../bp-13.png
```

### Local machine (explicit adapter URL)

```
./testLlavaInstall.sh \
  --adapter-url "https://mcswsnfzk7f1h5-9188.proxy.runpod.net/analyze" \
  --img /home/andy/.../bp-13.png
```

---

## Command‑line options

```
--img PATH                 Image file to test
--question TEXT            Prompt sent to LLaVA
--model-name NAME          Model name (default: llava-v1.5-7b)

--adapter-url URL          Adapter /analyze endpoint
--podid PODID              RunPod pod ID (used to build proxy URL)

--controller-url URL       Override controller URL (pod mode)
--worker-url URL           Override worker URL (pod mode)

--max-time SECONDS         Curl timeout for adapter test
--help                     Show built‑in usage reminder
```

---

## Expected success output

A successful run will end with:

```
ALL TESTS PASSED
```

Each section prints its raw or `jq`‑formatted JSON output so failures can be diagnosed immediately.

---

## Common failure hints

* **Models list is empty**

  * Worker is not registered with the controller
  * Model path or `MODEL_PATH` is incorrect

* **Adapter returns HTTP 500**

  * Adapter calling Gradio endpoints (deprecated)
  * Worker not reachable from adapter

* **ImageData validation errors**

  * Gradio API mismatch (reason adapter now bypasses Gradio)

---

## Design notes

* The adapter is intentionally tested **without Gradio** to avoid version skew between:

  * `gradio`
  * `gradio_client`
  * `pydantic`

* The worker test uses the **native LLaVA worker API** (`/worker_generate[_stream]`), which is the most stable integration point.

---

If this smoke test passes, the LLaVA stack is considered **operational** and ready for higher‑level tools such as `promptFromPhoto.py`.

---

## LLaVA Installation Smoke Test

Before debugging higher-level tools (e.g. `promptFromPhoto.py`, adapters, or batch pipelines), always verify the **core LLaVA stack** is healthy.

Use the smoke test script:

```
testLlavaInstall.sh
```

### When to run this

Run this test:

* After provisioning a **new RunPod**
* After running or modifying **`70_llava.sh`**
* After changing **model paths**, **conda envs**, or **dependencies**
* Before investigating adapter- or client-side errors

### What it checks

Depending on where it is run, the script automatically performs:

**On the pod (`/workspace` detected):**

* Port listeners (7001 controller, 7002 worker, 7003 web, 9188 adapter)
* Controller API:

  * `POST /list_models`
  * `POST /get_worker_address`
* Worker API:

  * `POST /worker_generate`
  * fallback to `/worker_generate_stream`
* Adapter API:

  * `POST /analyze` with multipart image upload

**On a local machine:**

* Adapter API via RunPod proxy

### Image handling

* On the pod, if `--img` is not supplied, the script automatically selects the **first `*.png`** in `/workspace`.
* On local, `--img` is required.

### Typical usage

**Pod (automatic image):**

```
./testLlavaInstall.sh
```

**Pod (explicit image):**

```
./testLlavaInstall.sh --img /workspace/bp-13.png
```

**Local (via PODID):**

```
./testLlavaInstall.sh --podid <PODID> --img /path/to/image.png
```

### Expected result

A healthy system ends with:

```
ALL TESTS PASSED
```

If this test fails, fix the reported layer (controller, worker, or adapter) **before** continuing with higher-level debugging.

For full details, see the **LLaVA Installation Smoke Test** documentation.
