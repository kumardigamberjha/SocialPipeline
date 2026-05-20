#!/bin/bash
# ═══════════════════════════════════════════════════════════════
# Wings of AI — ComfyUI Setup Script
# System: HP OMEN / RTX 4060 8GB / Ubuntu 24.04 LTS
# ═══════════════════════════════════════════════════════════════

set -e
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}━━━ Wings of AI — ComfyUI Setup ━━━${NC}"
echo -e "${CYAN}System: RTX 4060 8GB / Ubuntu 24.04${NC}\n"

# ── 1. NVIDIA Driver check ───────────────────────────────────
echo -e "${YELLOW}[1/6] Checking NVIDIA drivers...${NC}"
if ! nvidia-smi &>/dev/null; then
  echo "Installing NVIDIA drivers..."
  sudo ubuntu-drivers autoinstall
  sudo reboot
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
echo -e "${GREEN}✓ GPU ready${NC}\n"

# ── 2. CUDA Toolkit ──────────────────────────────────────────
echo -e "${YELLOW}[2/6] Checking CUDA...${NC}"
if ! nvcc --version &>/dev/null; then
  echo "Installing CUDA toolkit..."
  sudo apt install -y nvidia-cuda-toolkit
fi
nvcc --version | head -1
echo -e "${GREEN}✓ CUDA ready${NC}\n"

# ── 3. Clone ComfyUI ─────────────────────────────────────────
echo -e "${YELLOW}[3/6] Setting up ComfyUI...${NC}"
cd ~
if [ ! -d "ComfyUI" ]; then
  git clone https://github.com/comfyanonymous/ComfyUI.git
fi
cd ComfyUI

# ── 4. Python venv + deps ────────────────────────────────────
echo -e "${YELLOW}[4/6] Installing Python dependencies...${NC}"
rm -rf .venv
python3.12 -m venv .venv
source .venv/bin/activate

# PyTorch with CUDA 12.1 — correct for RTX 4060
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}\n"

# ── 5. ComfyUI Manager + GGUF node ───────────────────────────
echo -e "${YELLOW}[5/6] Installing custom nodes...${NC}"
cd custom_nodes

# ComfyUI Manager (install models from UI)
if [ ! -d "ComfyUI-Manager" ]; then
  git clone https://github.com/ltdrdata/ComfyUI-Manager.git
fi

# GGUF node (required for Flux.1-schnell quantized)
if [ ! -d "ComfyUI-GGUF" ]; then
  git clone https://github.com/city96/ComfyUI-GGUF.git
  cd ComfyUI-GGUF && pip install -r requirements.txt && cd ..
fi

echo -e "${GREEN}✓ Custom nodes ready${NC}\n"

# ── 6. Download models ───────────────────────────────────────
echo -e "${YELLOW}[6/6] Downloading models...${NC}"
cd ~/ComfyUI/models

# SDXL-Turbo (3.4GB) — fast option, ~3s per image
mkdir -p checkpoints
echo "Downloading SDXL-Turbo fp16..."
if [ ! -f "checkpoints/sd_xl_turbo_1.0_fp16.safetensors" ]; then
  wget -q --show-progress \
    "https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors" \
    -O checkpoints/sd_xl_turbo_1.0_fp16.safetensors
fi

# Flux.1-schnell Q4 (for better quality, ~7.9GB VRAM)
mkdir -p unet
echo -e "\n${CYAN}For Flux.1-schnell (better quality), run manually:${NC}"
echo "  cd ~/ComfyUI/models/unet"
echo "  wget https://huggingface.co/city96/FLUX.1-schnell-gguf/resolve/main/flux1-schnell-Q4_K_M.gguf"
echo ""
echo "  # Also need CLIP models in ~/ComfyUI/models/clip/"
echo "  wget https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp8_e4m3fn.safetensors"
echo "  wget https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/clip_l.safetensors"
echo ""
echo "  # And VAE in ~/ComfyUI/models/vae/"
echo "  wget https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors"

echo -e "${GREEN}✓ SDXL-Turbo ready${NC}\n"

# ── Create start script ──────────────────────────────────────
cat > ~/start_comfy.sh << 'EOF'
#!/bin/bash
cd ~/ComfyUI
source .venv/bin/activate
# --highvram = use full 8GB, no offloading (best for RTX 4060 8GB)
python main.py \
  --listen 0.0.0.0 \
  --port 8188 \
  --highvram \
  --cuda-device 0
EOF
chmod +x ~/start_comfy.sh

echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo -e "Start ComfyUI:  ${CYAN}~/start_comfy.sh${NC}"
echo -e "Web UI:         ${CYAN}http://localhost:8188${NC}"
echo -e "API endpoint:   ${CYAN}http://localhost:8188/prompt${NC}"
echo ""
echo -e "Then test the integration:"
echo -e "  ${CYAN}cd ~/wings-of-ai && python comfy_client.py${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
