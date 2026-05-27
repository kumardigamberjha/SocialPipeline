# Nexus Wings of AI – Autonomous Content Pipeline
## Project Documentation & Architecture Blueprint

This document provides a comprehensive, deep-dive specification of the **Nexus Wings of AI** project. It is structured to serve as a complete system blueprint that can be fed into any Large Language Model (LLM) to give it a full, detailed understanding of the project's requirements, APIs, backend agent workflow, frontend interface, database schemas, and external integrations.

---

## Table of Contents
1. [Project Overview & Core Vision](#1-project-overview--core-vision)
2. [System Architecture & Working Directory Structure](#2-system-architecture--working-directory-structure)
3. [Environment Configuration & Requirements](#3-environment-configuration--requirements)
4. [Multi-Agent Orchestration Syndicate (CrewAI)](#4-multi-agent-orchestration-syndicate-crewai)
5. [FastAPI Backend API Specifications](#5-fastapi-backend-api-specifications)
6. [WebSocket Streaming Protocols](#6-websocket-streaming-protocols)
7. [Vector Memory & RAG Integration (Qdrant)](#7-vector-memory--rag-integration-qdrant)
8. [Relational Database Telemetry Schema (SQLite)](#8-relational-database-telemetry-schema-sqlite)
9. [ComfyUI Visual Synthesis Engine (SDXL Turbo / Flux Schnell)](#9-comfyui-visual-synthesis-engine-sdxl-turbo--flux-schnell)
10. [Next.js 14/16 Frontend Command Nexus](#10-nextjs-1416-frontend-command-nexus)

---

## 1. Project Overview & Core Vision

**Nexus Wings of AI** is an autonomous, full-stack content generation pipeline designed to solve the bottlenecks of multi-platform branding (specifically for DevRel engineers, tech creators, and founders). 

Instead of simple prompt-and-response text generation, this system orchestrates a **syndicate of 10 specialized CrewAI agents** that run sequentially. It takes a single tech topic (or autonomously scrapes the latest viral tech news using DuckDuckGo/Hacker News APIs) and produces a complete social media campaign ready for production, including:
- 5 viral developer topics with justifications.
- A fully structured, retention-optimized YouTube script.
- YouTube SEO tags, titles, and descriptions.
- Dynamic high-CTR YouTube thumbnail design concepts.
- A fast-paced, vertical YouTube Shorts/TikTok script (under 60s).
- An engaging LinkedIn post written in professional storytelling style (with punchy formatting and hashtags).
- A cohesive, viral X (Twitter) thread.
- An in-depth technical blog post containing practical code examples.
- A progressive, structured programming course outline.
- 10 secondary creative content ideas to extend campaign longevity.
- High-resolution visual assets synthesized via ComfyUI (SDXL Turbo or Flux.1 Schnell) optimized for Instagram (1080x1350, 4:5 aspect ratio).

---

## 2. System Architecture & Working Directory Structure

The system uses a decoupled microservices pattern:
- **Backend:** Python + FastAPI + Uvicorn + CrewAI + LangChain.
- **Frontend:** TypeScript + Next.js (App Router) + TailwindCSS + Framer Motion.
- **Persistent Data & Telemetry:** SQLite3 for run logging, step execution telemetry, user registry, and API credentials.
- **Vector DB / RAG:** Qdrant Cloud (local/in-memory fallback) for conversational agent memory and document indexing.
- **Image Generation Node:** ComfyUI executing on an RTX 4060 GPU with custom checkpoint and GGUF model workflows.

### Repository Directory Map
```text
.
├── app/                        # FastAPI Backend Application
│   ├── api/                    # Core API routes logic
│   ├── core/                   # Shared system utilities & logic
│   ├── db/                     # Data stores
│   │   ├── qdrant.py           # Vector database setup & embedding retrieval
│   │   └── supabase.py         # Relational database client & schema inserts
│   ├── routers/                # FastAPI routing layers
│   │   ├── auth.py             # User register/login handlers
│   │   ├── generate.py         # REST pipeline triggers
│   │   ├── health.py           # System status endpoints
│   │   ├── instagram.py        # ComfyUI HTTP/WS image endpoints
│   │   ├── memory.py           # Qdrant user memory routers
│   │   ├── rag.py              # Text document indexing endpoints
│   │   ├── runs.py             # Telemetry history fetchers
│   │   └── ws.py               # Live-stream pipeline sockets
│   ├── services/               # Business logic integrations
│   │   ├── agents/             # Custom agents
│   │   └── comfy_client.py     # ComfyUI API & workflow orchestrator
│   ├── tools/                  # Custom tools for CrewAI agents
│   │   └── custom.py           # DDG search, local reader, sandboxed sandbox executor, DB placeholders
│   ├── config.py               # Unified settings container (Pydantic Settings)
│   ├── crew.py                 # Core orchestration pipeline assembly & fallback routing
│   ├── llm.py                  # Multi-provider LLM instance builder (NVIDIA NIM / Groq / Ollama)
│   ├── logging_config.py       # Custom server logging setup
│   ├── main.py                 # FastAPI application factory entrypoint
│   ├── schemas.py              # Pydantic request & response validation structures
│   └── ws_manager.py           # WebSocket client connection manager
├── dashboard/                  # Next.js Frontend Dashboard
│   ├── public/                 # Static assets
│   │   └── generated_posts/    # Destination directory for generated ComfyUI images
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css     # Dark mode style rules
│   │   │   ├── layout.tsx      # Root html shell & font loading
│   │   │   └── page.tsx        # Command Nexus central UI layout
│   │   ├── components/         # Glassmorphic component elements
│   │   │   ├── AgentPipeline.tsx   # Live visual progress monitor for agents
│   │   │   ├── ApprovalQueue.tsx   # Topic submission, stream log screen, asset actions
│   │   │   ├── Header.tsx      # Health checkers & system metrics indicators
│   │   │   └── TelemetryLedger.tsx # Historical database logger list
│   │   └── lib/
│   │       └── api.ts          # Type-safe Next fetch client
│   ├── tsconfig.json           # TS Compiler Rules
│   └── package.json            # Node project configuration
├── generated_posts/            # Alternative backup storage folder
├── requirements.txt            # Python dependencies manifest
├── start_comfy.sh              # Local shell utility to launch ComfyUI on CUDA
└── first_agent.py              # Baseline testing module for CrewAI setup
```

---

## 3. Environment Configuration & Requirements

### Backend Python Requirements (`requirements.txt`)
- `fastapi>=0.115.0`
- `uvicorn[standard]>=0.34.0`
- `crewai>=0.100.0`
- `python-dotenv>=1.0.0`
- `pydantic-settings>=2.6.0`
- `supabase>=2.3.0`
- `qdrant-client>=1.7.0`
- `websockets>=12.0`
- `duckduckgo-search` (Optional fallback for search tool)
- `aiohttp`, `websockets` (For ComfyUI client loop)

### System Environment Variables (`app/.env`)
The backend looks at `app/.env` at runtime using Pydantic Settings:
```env
# LLM Provider Keys
NVIDIA_API_KEY=nvapi-your-nvidia-nim-token
GROQ_API_KEY=gsk_your-groq-api-key

# Database Configurations (SQLite)
SQLITE_DB_PATH=./data/nexus.db
SECRET_KEY=change-this-to-a-random-64-char-string-in-production
SUPABASE_URL=https://your-supabase-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
SUPABASE_PROJECT_LINK=https://your-supabase-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your-supabase-anon-key
SUPABASE_SECRET_KEY=your-supabase-service-role-key
SUPABASE_DB_CONNECTION_STRING=postgresql://postgres:your-db-password@db.your-supabase.supabase.co:5432/postgres

# Vector Storage (Qdrant Cloud)
QDRANT_URL=https://your-qdrant-cluster.aws.qdrant.io
QDRANT_API_KEY=your-qdrant-access-key
QDRANT_CLUSTER_ENDPOINT=https://your-qdrant-cluster.aws.qdrant.io
QDRANT_CLUSTER_KEY=your-qdrant-access-key

# Configuration Overrides
DEFAULT_PROVIDER=nvidia # Default provider ("nvidia", "groq", "ollama")
LLM_TEMPERATURE=0.6
LLM_MAX_TOKENS=4096
LLM_TIMEOUT=300
OLLAMA_MODEL=ollama_chat/qwen2.5-coder:latest
OLLAMA_API_BASE=http://localhost:11434
```

### Frontend Configuration (`dashboard/.env`)
```env
NEXT_PUBLIC_BACKEND_API=http://127.0.0.1:8000
```

---

## 4. Multi-Agent Orchestration Syndicate (CrewAI)

The central pipeline is managed via `app/crew.py`. When a request is triggered:
1. **Topic Enrichment:** The system runs a pre-run search via DuckDuckGo or Hacker News (Algolia API) on the query before kickoff. This pre-run context is directly injected into the core user prompt, mitigating search tool execution failures within individual agent loops.
2. **Memory Injector:** The workspace queries Qdrant DB for past user logs and indexed RAG documents related to the topic, injecting context.
3. **Execution Plan:** It constructs 10 agents and maps them to 10 sequential tasks.
4. **Resiliency Fallback Routing:**
   - The pipeline tries the primary selected provider (e.g., NVIDIA NIM using `stepfun-ai/step-3.5-flash`).
   - If NVIDIA fails, the backend catches the exception and hot-swaps the LLM engine to the fallback provider (e.g., Groq using `llama-3.3-70b-versatile`) and restarts the crew without losing the client session.
   - Ollama (running locally with `qwen2.5-coder:latest`) is also supported. Note that for Ollama, tools are stripped to ensure faster, offline generation.

### Roster of Agents (`app/agents.py` & `app/tasks.py`)

| # | Agent Role (Name) | Backstory / Goal | Specialized Tools | Expected Task Output |
|---|---|---|---|---|
| 1 | **Senior Tech Trend Analyst** | AI content strategist. Goal is to analyze the topic news and identify 5 high-CTR, viral developer topics. | `web_search_tool` | A list of 5 trending tech topics with detailed justifications. |
| 2 | **YouTube Script Writer** | Scriptwriter. Goal is to design a YouTube video script with an engaging hook in the first line and CTA. | None | A complete YouTube script with scene details and narration. |
| 3 | **SEO Specialist** | YouTube SEO expert. Goal is to generate rankable metadata based on the script. | `web_search_tool` | An optimized video title, structured description, and 10+ tags. |
| 4 | **Thumbnail Designer** | Graphic strategist. Goal is to create curiosity-driven visual prompts and layouts for thumbnails. | None | Detailed CTR-optimized thumbnail concepts with descriptions. |
| 5 | **Shorts Script Writer** | Short-form architect. Goal is to write punchy scripts under 60 seconds. | None | A fast-paced vertical video script with visual hook tags. |
| 6 | **LinkedIn Content Creator** | Growth writer. Goal is to generate high-engagement posts in "broetry" style. | None | A professional LinkedIn post using storytelling hook lines. |
| 7 | **Twitter Thread Writer** | Micro-blogger. Goal is to design structured, highly shareable threads. | None | A multi-tweet thread starting with a high-curiosity hook. |
| 8 | **Technical Blogger** | Tech publisher. Goal is to write clear developer posts with code examples. | `file_reader_tool`, `code_execution_tool` | An in-depth blog post with markdown headers and block examples. |
| 9 | **Course Architect** | Educator. Goal is to design structured learning modules for developers. | None | A full curriculum outline showing modules, targets, and goals. |
| 10 | **Creative Content Strategist** | Viral strategist. Goal is to extend content life with secondary viral ideas. | `web_search_tool`, `api_request_tool`, `db_query_tool` | A list of 10 creative ideas for cross-platform expansion. |

*Note: An eleventh agent (`Instagram Image Designer`) is defined in `app/agents.py` to handle visual synthesis requests dynamically via ComfyUI.*

---

## 5. FastAPI Backend API Specifications

The REST API exposes the following endpoints (implemented in `app/routers/`):

### 5.1 System Health
- **Endpoint:** `GET /api/health`
- **Purpose:** Monitor system health and list available LLM models.
- **Request Headers:** None
- **Response Schema (`HealthResponse`):**
  ```json
  {
    "status": "healthy",
    "app_name": "Wings of AI – Content Pipeline",
    "version": "1.0.0",
    "providers": ["nvidia", "groq", "ollama"],
    "agents_available": 10
  }
  ```

### 5.2 Content Generation (Synchronous REST)
- **Endpoint:** `POST /api/generate`
- **Purpose:** Synchronously trigger all 10 agents sequentially and return the final compiled payload.
- **Request Body (`GenerateRequest`):**
  ```json
  {
    "topic": "FastAPI WebSockets vs HTTP",
    "provider": "nvidia"
  }
  ```
- **Response Schema (`GenerateResponse`):**
  ```json
  {
    "status": "success",
    "topic": "FastAPI WebSockets vs HTTP",
    "provider_used": "nvidia",
    "duration_seconds": 142.35,
    "result": "## Trend Analysis\n... ## YouTube Script\n... ## LinkedIn Post\n..."
  }
  ```

### 5.3 User Authentication
- **Endpoint:** `POST /api/auth/register`
- **Purpose:** Register new users using bcrypt password hashing and PyJWT, storing them into the `users` SQLite database.
- **Request Body:**
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword123"
  }
  ```
- **Response:**
  ```json
  {
    "user": { "id": "uuid-string", "email": "user@example.com" },
    "session": { "access_token": "jwt-token-string", "refresh_token": "..." }
  }
  ```

- **Endpoint:** `POST /api/auth/login`
- **Purpose:** Authenticate users using password credentials.
- **Request Body:** Same as register.
- **Response:** Same as register.

### 5.4 Vector Memory Management (Qdrant)
- **Endpoint:** `POST /api/memory/save`
- **Purpose:** Save custom styled context or facts to Qdrant memory collection.
- **Request Body:**
  ```json
  {
    "user_id": "user-uuid-string",
    "text": "The developer prefers void_purple backgrounds and hates emojis in LinkedIn posts."
  }
  ```
- **Response:** `{"status": "success"}`

- **Endpoint:** `POST /api/memory/search`
- **Purpose:** Retrieve user-specific styling rules to inject into the LLM context.
- **Request Body:**
  ```json
  {
    "user_id": "user-uuid-string",
    "query": "LinkedIn writing style preferences"
  }
  ```
- **Response:**
  ```json
  {
    "results": [
      "The developer prefers void_purple backgrounds and hates emojis in LinkedIn posts."
    ]
  }
  ```

### 5.5 Document RAG Storage (Qdrant)
- **Endpoint:** `POST /api/rag/upload`
- **Purpose:** Upload and index a text document for retrieval.
- **Request Content-Type:** `multipart/form-data`
- **Parameters:** `user_id` (Form Field), `file` (UploadFile)
- **Response:** `{"status": "success", "message": "filename.txt embedded successfully."}`

- **Endpoint:** `POST /api/rag/query`
- **Purpose:** Query uploaded document context.
- **Request Body:**
  ```json
  {
    "user_id": "user-uuid-string",
    "query": "fastapi websocket implementation details"
  }
  ```
- **Response:**
  ```json
  {
    "results": ["FastAPI contains a WebSocket class for handling connections..."]
  }
  ```

### 5.6 Telemetry Ledger History (SQLite)
- **Endpoint:** `GET /api/runs`
- **Purpose:** Fetch historical metadata of all runs logged in SQLite.
- **Query Parameter:** `limit` (default: 50)
- **Response:** Array of run records (ordered by newest first):
  ```json
  [
    {
      "id": "run-uuid-string",
      "user_id": "user-uuid-string",
      "topic": "FastAPI WebSockets vs HTTP",
      "provider_used": "nvidia",
      "status": "completed",
      "final_result": "...",
      "duration_seconds": 124.5,
      "completed_at": "2026-05-27T12:00:00Z",
      "created_at": "2026-05-27T11:58:00Z"
    }
  ]
  ```

### 5.7 ComfyUI Instagram Generator
- **Endpoint:** `POST /api/instagram/generate`
- **Purpose:** Direct REST endpoint to request ComfyUI to synthesize a background post image.
- **Request Body (`InstagramGenerateRequest`):**
  ```json
  {
    "topic": "AI Coding Assistant System",
    "palette": "void_purple",
    "layout": "bottom_hero",
    "model": "sdxl_turbo",
    "style_hints": "hyperdetailed, cinematic depth",
    "seed": 42
  }
  ```
- **Response:**
  ```json
  {
    "prompt_id": "comfyui-job-uuid",
    "positive_prompt": "(Instagram post background for AI Coding Assistant System), deep purple neon cyberpunk atmosphere...",
    "negative_prompt": "text, watermark, logo...",
    "model": "sdxl_turbo",
    "palette": "void_purple",
    "layout": "bottom_hero",
    "images": ["base64_encoded_image_string..."],
    "duration_s": 3.42
  }
  ```

---

## 6. WebSocket Streaming Protocols

Since executing the full CrewAI agent pipeline can take up to 2-3 minutes, the backend uses WebSockets to stream granular progress updates in real-time.

### 6.1 Agent Execution Stream
- **Path:** `/api/ws/generate/{client_id}`
- **Establishment:** Client opens the WebSocket and sends a trigger JSON:
  ```json
  {
    "topic": "Developing Custom CrewAI Tools",
    "provider": "nvidia"
  }
  ```

- **Path (Auto-Research):** `/api/ws/auto-generate/{client_id}`
- **Establishment:** Client opens the WebSocket and triggers an automated trend search:
  ```json
  {
    "provider": "nvidia"
  }
  ```
  *Note: The backend automatically searches Hacker News/DuckDuckGo for trending keywords and runs the pipeline on the #1 trending topic.*

#### WebSocket Server Events Emitted to Client:
1. **Status Start Notification:**
   ```json
   {
     "type": "status",
     "message": "Pipeline started"
   }
   ```
2. **Task Execution Activated:**
   ```json
   {
     "type": "task_started",
     "task": "Find 5 viral topics related to Developing Custom CrewAI Tools."
   }
   ```
3. **Task Completion Log (Emitted after each of the 10 agents finishes):**
   ```json
   {
     "type": "task_finished",
     "task": "Trend Analysis",
     "output": "Here are 5 trending topics...\n1. Agent Tool sandboxing..."
   }
   ```
4. **Entire Pipeline Completed:**
   ```json
   {
     "type": "complete",
     "result": "## Full Content Package Markdown..."
   }
   ```
5. **Exception Handler Error Event:**
   ```json
   {
     "type": "error",
     "message": "Detailed stack trace or timeout details"
   }
   ```

### 6.2 ComfyUI Image Generation Stream
- **Path:** `/ws/instagram/generate`
- **Protocol Flow:**
  - Client sends `InstagramGenerateRequest` parameters in JSON.
  - Server sends: `{"type": "status", "message": "Building prompt..."}`
  - Server sends: `{"type": "prompt_ready", "prompt": "compiled positive prompt..."}`
  - Server sends: `{"type": "status", "message": "Queued on ComfyUI (sdxl_turbo)..."}`
  - Server sends: `{"type": "status", "message": "Generating image on RTX 4060..."}`
  - Server retrieves files, processes base64 strings, and sends:
    ```json
    {
      "type": "complete",
      "prompt_id": "comfy-uuid",
      "images": ["base64_data_1", "base64_data_2"],
      "prompt": "positive prompt string"
    }
    ```
  - Server closes connection.

---

## 7. Vector Memory & RAG Integration (Qdrant)

The vector integration is located in `app/db/qdrant.py`.
- **Collections:**
  - `memory_collection`: Stores user preferences and conversational context.
  - `rag_collection`: Stores embedded chunks of uploaded reference articles.
  - `docs_collection`: Reserved for codebase documentation indexing.
- **Parameters:** Custom vectors are configured with a size of **384 dimensions** (matching `all-MiniLM` local embeddings or standard mock structures) using **Cosine Distance**.
- **Payload Filtering:** Search queries use Qdrant Filter logic to match keyword fields (e.g., `user_id == req.user_id`) to ensure isolation in SaaS environments.

*Architectural Flag:* Qdrant is currently disabled in the setup via a mock return in `get_qdrant()`. It can be re-enabled by removing `return None` and pointing the configuration to a live Qdrant Cloud Cluster.

---

## 8. Relational Database Telemetry Schema (SQLite)

SQLite tracks history and logs. Below is the active schema layout mapping:

### 8.1 Table: `agent_runs`
Tracks the overall generation job status.
```sql
CREATE TABLE agent_runs (
    id UUID PRIMARY KEY,
    user_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,
    topic TEXT NOT NULL,
    provider_used TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    final_result TEXT,
    duration_seconds NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE
);
```

### 8.2 Table: `task_steps`
Tracks execution logs of individual agents.
```sql
CREATE TABLE task_steps (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID REFERENCES agent_runs(id) ON DELETE CASCADE,
    agent_name TEXT NOT NULL,
    task_name TEXT NOT NULL,
    output TEXT,
    status TEXT NOT NULL DEFAULT 'done',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
```

### 8.3 Table: `users`
Custom user ledger synced from auth triggers.
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
```

### 8.4 Table: `api_keys`
Stores encrypted API tokens for external LLMs in multi-tenant SaaS environments.
```sql
CREATE TABLE api_keys (
    id BIGSERIAL PRIMARY KEY,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    api_key_encrypted TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
);
```

---

## 9. ComfyUI Visual Synthesis Engine (SDXL Turbo / Flux Schnell)

The image generation client is located in `app/services/comfy_client.py`.
- **System Specifications:** Optimizations target local execution on an RTX 4060 8GB GPU on Ubuntu.
- **Output Directories:** Saved images are written to `dashboard/public/generated_posts/` with the file mask `{prompt_id}_{index}.png`.

### 9.1 Dynamic Design & Color Palettes
The script translates raw text topics into cinematic styles using predefined configuration vectors:

```python
PALETTE_MOODS = {
    "void_purple":  "deep purple neon cyberpunk atmosphere, violet bokeh, dark tech aesthetic, electric glow",
    "cyber_teal":   "bioluminescent teal glow, deep ocean dark tech, cyan light particles, glass refraction",
    "neon_coral":   "warm coral sunset editorial, neon pink digital art, soft bokeh energy, warm tones",
    "solar_amber":  "golden amber cinematic light, sunrise tech, warm bokeh lens flares, editorial magazine",
    "ice_blue":     "crisp ice blue cold light, frost glass texture, arctic tech atmosphere, clean sharp",
    "forest":       "emerald bioluminescent forest, green data streams, organic tech fusion, deep rich green",
    "crimson":      "deep crimson dramatic lighting, red glowing particles, dark editorial, intense atmosphere",
    "pure_dark":    "ultra clean monochrome, black white high contrast, film grain, studio editorial",
}
```

### 9.2 Layout Compositions
Configured to optimize negative space for graphic text overlay:
```python
LAYOUT_COMPOSITIONS = {
    "bottom_hero":  "wide cinematic background, strong visual interest in upper 60%, clear negative space bottom third for text overlay",
    "top_title":    "vertical portrait composition, visual anchor at center, open clear space at top quarter",
    "center_bold":  "perfectly centered radial composition, symmetrical focal point, dramatic center depth",
    "split_left":   "asymmetric rule-of-thirds, main subject right-weighted, left side open negative space",
    "minimal":      "70 percent negative space, single dramatic focal point, extreme minimalist zen composition",
    "full_text":    "abstract layered texture, blurred bokeh depth field, atmospheric background pattern",
}
```

### 9.3 Supported Generation Workflows
1. **SDXL Turbo Workflow:**
   - **Model:** `sd_xl_turbo_1.0_fp16.safetensors`
   - **Sampler:** `euler_ancestral` with `karras` scheduler.
   - **Settings:** Steps = 4, CFG = 1.0, Denoise = 1.0.
   - **VRAM Signature:** Highly optimized, execution time is ~3 seconds.
2. **Flux.1 Schnell Workflow (GGUF):**
   - **Model:** `flux1-schnell-Q4_K_M.gguf` loaded via `UnetLoaderGGUF`.
   - **Clip Loaders:** `t5xxl_fp8_e4m3fn.safetensors` & `clip_l.safetensors`.
   - **VAE:** `ae.safetensors`.
   - **Sampler:** `euler` sampler using `BasicScheduler` (simple).
   - **Settings:** Steps = 4, Denoise = 1.0, CFG = 1.0.
   - **VRAM Signature:** Consumes ~7GB VRAM. Running on an RTX 4060 8GB takes ~8 seconds.

---

## 10. Next.js 14/16 Frontend Command Nexus

The dashboard UI uses `framer-motion` for micro-animations and `lucide-react` for system iconography.

### 10.1 UI Component Architecture

1. **`Header.tsx` (Status Watcher):**
   - Polling hook executes `/api/health` queries every 30 seconds.
   - Renders a pulsing green ring ("System Online") if HTTP 200 returns successfully, or a solid red ring ("System Offline") if the request fails.
   - Displays the current active agent count.
2. **`AgentPipeline.tsx` (Progress Tracker):**
   - Renders a horizontal card layout mapping all 10 CrewAI agents.
   - Transitions individual nodes between three states:
     - `idle` (grey borders, static icons).
     - `active` (blue pulsing border, active scanning line animation, sliding progress indicator).
     - `complete` (green borders, green glowing shadows).
3. **`ApprovalQueue.tsx` (Command Center):**
   - Holds state for the client input topic.
   - Handles connection state for WebSockets (`/api/ws/generate/{client_id}` or `/api/ws/auto-generate/{client_id}`).
   - Streams text outputs into a terminal console container.
   - Renders final copyable markdown content and handles image generation configurations (palette, layout, model).
   - Updates generation progress variables (`isGenerating` / `completedTasks`) to synchronize with the `AgentPipeline` UI.
4. **`TelemetryLedger.tsx` (Run History Table):**
   - Fetches historical telemetry lists from `/api/runs`.
   - Displays a grid displaying the topic, status badge (completed, running, failed), and mock metric fields (Impressions, Likes, Comments, CTR).
   - Click handlers allow rows to expand, revealing the full markdown content of the run.
