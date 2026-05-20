# 🚀 Nexus Wings of AI – Autonomous Content Pipeline

![Nexus Wings of AI Dashboard](https://raw.githubusercontent.com/kumardigamberjha/SocialPipeline/main/nexus_wings_ai_dashboard_mockup.png)
*(Mockup of the Holographic Neural Matrix Dashboard)*

> [!TIP]
> **New to Nexus Wings of AI?** Check out our deep-dive [Case Study](file:///media/digamber-jha/G/MyEmpire/Linkedin%20Post%20Generator/CASE_STUDY.md) to understand the architecture, agent roles, and business value behind this autonomous pipeline.

Welcome to the **Nexus Wings of AI** repository! This project is an end-to-end, full-stack, AI-powered Autonomous Content Generation platform tailored specifically for developer relations, personal branding, and multi-platform distribution.

## 🌟 Vision
Instead of a simple "prompt-and-completion" app, this system orchestrates a **dynamic crew of AI Agents** (via CrewAI) and executes an iterative, streaming pipeline. It doesn't just write text; it researches, strategizes, and generates visual assets across multiple platforms.

## ⚡ Core Features
- 🔍 **Auto-Research Magic**: Conducts real-time Web Searches using DuckDuckGo to find trending tech news.
- 🎬 **Multi-Platform Scripts**: Drafts long-form YouTube scripts and engaging YouTube Shorts (under 60s).
- 📈 **SEO Optimization**: Extracts metadata, tags, and designs high-CTR Thumbnail visual prompts.
- 👔 **Professional Branding**: Crafts high-converting LinkedIn posts and viral X (Twitter) threads.
- 🎨 **Visual AI Engine**: Integrated **ComfyUI (SDXL Turbo / Flux Schnell)** for generating high-end social media assets.
- ⚡ **Real-Time Streaming**: Granular progress of each agent via WebSockets straight to a glassmorphic Next.js Dashboard.
- 🧠 **Memory & RAG**: Long-term user memories via **Qdrant Cloud** for hyper-personalized content.

---

## 🏗 System Architecture

The system is built as a distributed microservices architecture for maximum scalability and performance.

### 🖥 Backend (Python/FastAPI)
- **Framework:** `FastAPI` (Asynchronous HTTP & WebSocket routing).
- **Orchestration:** `CrewAI` & `LangChain` for multi-agent collaboration.
- **LLM Routing:** Intelligent fallback between **NVIDIA NIM** (`Llama 3.1 405B`) and **Groq** (`Llama 3.1 70B`).
- **Telemetry:** **Supabase (PostgreSQL)** for tracking `agent_runs` and `task_steps`.
- **Vector Store:** **Qdrant Cloud** for RAG and persistent agent memory.
- **Image Gen:** Integrated **ComfyUI** client for local/remote GPU image synthesis.

### 🎨 Frontend (TypeScript/Next.js)
- **Framework:** `Next.js 14` (App Router).
- **Design System:** `TailwindCSS` with custom glassmorphism and holographic aesthetics.
- **Motion:** `framer-motion` for fluid node-activation sequences and real-time UI updates.
- **Delivery:** Custom `WebSocket` hooks for low-latency pipeline progress visualization.

---

## 📁 Project Structure

```text
.
├── app/                  # FastAPI Backend
│   ├── api/              # API Route Logic
│   ├── core/             # Core Engine & LLM Config
│   ├── db/               # Database Models (Supabase)
│   ├── routers/          # FastAPI Route Handlers
│   ├── services/         # Business Logic (ComfyUI Client, etc.)
│   └── tools/            # Custom CrewAI Tools
├── dashboard/            # Next.js Frontend
│   ├── src/app/          # Page Components
│   ├── src/components/   # Reusable UI Components
│   └── public/           # Static Assets
├── generated_posts/      # Output Storage
├── start_comfy.sh        # Script to initialize Image Gen Engine
└── requirements.txt      # Python Dependencies
```

---

## 🛠 Prerequisites
Ensure you have the following installed on an Ubuntu/Linux machine:
- **Python 3.10+**
- **Node.js 18+** & **npm**
- **ComfyUI** (Optional, for image generation)
- API Keys: NVIDIA NIM, Groq, Supabase, and Qdrant Cloud.

---

## 🚀 Setup Instructions

### 1. Backend Configuration
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Create `app/.env` with your API keys (see `app/config.py` for required fields).

### 2. Frontend Configuration
```bash
cd dashboard/
npm install
```
Create `dashboard/.env`:
```env
NEXT_PUBLIC_BACKEND_API=http://127.0.0.1:8000
```

### 3. Database Migration
Run the SQL migration in your Supabase SQL Editor to initialize the telemetry tables:
```sql
CREATE TABLE agent_runs (id UUID PRIMARY KEY, topic TEXT, status TEXT, created_at TIMESTAMP);
-- See README.md (original) for full schema or check app/db/models.py
```

---

## 🏃 Execution

**Terminal 1 (Backend):**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 (Frontend):**
```bash
cd dashboard/
npm run dev
```

**Terminal 3 (Image Gen - Optional):**
```bash
./start_comfy.sh
```

---

*Built with ❤️ utilizing the absolute bleeding edge of Multi-Agent Orchestration.*

