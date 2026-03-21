# 🚀 Nexus Wings of AI – Autonomous Content Pipeline

Welcome to the **Wings of AI** repository! This project is an end-to-end, full-stack, AI-powered Autonomous Content Generation platform tailored specifically for developer relations, personal branding, and multi-platform distribution.

## 🌟 What is this?
Instead of a simple "prompt-and-completion" app, this system orchestrates a **dynamic crew of AI Agents** (via CrewAI) and executes an iterative, streaming pipeline. 

With one click (or "Auto-Research Magic"), the system:
1. Conducts real-time Web Searches using DuckDuckGo.
2. Drafts long-form YouTube scripts.
3. Extracts SEO-optimized metadata and tags.
4. Generates engaging YouTube Shorts scripts (under 60s).
5. Designs high-CTR Thumbnail visual prompts.
6. Crafts high-converting professional LinkedIn posts.
7. Writes viral, thread-style X (Twitter) threads.

All of this happens live, streaming the granular progress of each agent via WebSockets straight to a beautifully designed Next.js Holographic Dashboard!

---

## 🏗 System Architecture

This project is rigidly detached across a FastAPI microservices backend and a Next.js App Router frontend for maximum scalability.

### 🖥 The Backend (Python/FastAPI)
- **Framework:** `FastAPI` (Asynchronous HTTP & WebSocket routing).
- **Core Engine:** `CrewAI` & `Langchain` connecting modular `Agent` and `Task` declarations.
- **LLM Routing:** Easily switchable fallback logic between **NVIDIA** (`meta/llama-3.1-405b-instruct`) and **Groq** (`llama-3.1-70b-versatile`).
- **Data Persistence (Relational):** **Supabase (PostgreSQL)**. Used to securely trace every `agent_run` and granular `task_step` for long-term telemetry metrics.
- **Vector Database (RAG & Memory):** **Qdrant (Cloud)**. Enables long-term user memories and contextual RAG document injections during generation to keep content heavily personalized.

### 🎨 The Frontend (TypeScript/Next.js)
- **Framework:** `Next.js 14` (App Router).
- **Styling:** `TailwindCSS` with custom glassmorphism, neo-brutalism, and holographic theme aesthetics.
- **Animations:** Fully powered by `framer-motion` for fluid, real-time node activation sequences.
- **Real-Time Delivery:** Custom `WebSocket` hooks that listen for `task_started`, `task_finished`, and `complete` events to render the pipeline UI organically.

---

## 🛠 Prerequisites

Before starting, ensure you have the following installed on an Ubuntu/Linux machine:
1. `Python 3.10+`
2. `Node.js 18+` & `npm`
3. A **Supabase** account (Free tier is perfectly fine).
4. A **Qdrant Cloud** cluster (Free tier is perfectly fine).
5. API Keys for **NVIDIA NIM**, **Groq**, and **OpenAI/Anthropic** (Optional).

---

## 🚀 Setup Instructions

### Step 1: Clone & Configure the Backend

Navigate to the project root and create your Python Virtual Environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Backend Environment Configuration
Create a `.env` file inside the `app/` folder (`app/.env`):
```env
# Multi-LLM Routing
NVIDIA_API_KEY=nvapi-...
GROQ_API_KEY=gsk_...

# Qdrant Vector Cloud
QDRANT_CLUSTER_KEY=your_qdrant_api_key
QDRANT_CLUSTER_ENDPOINT=https://your-cluster-id.region.aws.cloud.qdrant.io

# Supabase Telemetry Tracking
SUPABASE_URL=https://your-project.supabase.co
# CRITICAL: Backend needs the secret/service_role key to bypass RLS!
SUPABASE_SECRET_KEY=eyJhbG... 
```

#### Supabase Database Initialization
Head to your Supabase SQL Editor and run the following migration to spin up the telemetry architecture:
```sql
CREATE TABLE IF NOT EXISTS public.agent_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    topic TEXT,
    provider_used TEXT,
    status TEXT DEFAULT 'running',
    final_result TEXT,
    duration_seconds FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE IF NOT EXISTS public.task_steps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES public.agent_runs(id) ON DELETE CASCADE,
    agent_name TEXT,
    task_name TEXT,
    status TEXT DEFAULT 'pending',
    output TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Mock anonymous user for unauthenticated generations
INSERT INTO auth.users (id, email) VALUES ('00000000-0000-0000-0000-000000000000', 'anonymous@example.com') ON CONFLICT (id) DO NOTHING;
```

### Step 2: Configure the Frontend

Navigate to the dashboard directory:
```bash
cd dashboard/
npm install
```

#### Frontend Environment Configuration
Create a `.env` file inside the `dashboard/` folder (`dashboard/.env`):
```env
NEXT_PUBLIC_BACKEND_API=http://127.0.0.1:8002
```
*(This ensures your dashboard dynamically requests the backend API without hardcoded dependencies.)*

---

## 🏃 Demo Level Execution Run!

To experience the full pipeline, fire up both development servers in separate terminals.

**Terminal 1 (Backend - FastAPI):**
```bash
source .venv/bin/activate
export PYTHONPATH=$PYTHONPATH:$(pwd)
uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
```
*(Watch the console print "Initialized Supabase" and "Initialized Qdrant collections".)*

**Terminal 2 (Frontend - Next.js):**
```bash
cd dashboard/
npm run dev
```

### 🎯 Experiencing the UI
1. Navigate to **`http://localhost:3000`** in your browser.
2. You'll see the gorgeous holographic Neural Matrix.
3. **Manual Generation**: Type a topic into the input field (e.g., "Mojo Programming Language 2026") and click the Play icon. Watch the nodes light up as each CrewAI agent sequentially researches and drafts content.
4. **Auto-Research Magic**: Click the purple button. The system bypasses your input, scrapes DuckDuckGo for the `#1 Viral Tech News` today, and autonomously runs the entire pipeline based on what's trending.
5. **Telemetry Ledger:** Scroll to the bottom of the dashboard. History connects automatically to Supabase via `GET /api/runs`, populating an animated accordion list of all historical outputs that you can easily copy and export!

---

*Built with ❤️ utilizing the absolute bleeding edge of Multi-Agent Orchestration.*
