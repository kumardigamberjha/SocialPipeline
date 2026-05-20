#!/bin/bash
cd ~/ComfyUI || { echo "ComfyUI directory not found!"; exit 1; }
source .venv/bin/activate
# --highvram = use full 8GB, no offloading (best for RTX 4060 8GB)
python main.py \
  --listen 0.0.0.0 \
  --port 8188 \
  --highvram \
  --cuda-device 0
