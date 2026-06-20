# Wings of AI — Autonomous Content Pipeline

> A multi-agent content generation platform that researches, writes, and publishes LinkedIn posts, long-form blog articles, and Instagram visuals — in real time, with full WebSocket streaming.

For a deep-dive into the architecture, agent roles, and business reasoning behind this system see [CASE_STUDY.md](./CASE_STUDY.md).

---

## Core Features

- **LinkedIn post pipeline** — five-agent chain: hook finder → post writer → editor → QA checker → approver, delivered to the client via live WebSocket events.
- **Blog post pipeline** — researcher fetches and summarises source URLs concurrently, then a writer drafts each section independently, followed by an editor, QA assembler, and approver.
- **Instagram image generation** — ComfyUI client (SDXL Turbo / Flux Schnell) triggered from the backend; polling loop pushes progress over WebSocket.
- **JWT authentication** — register / login with bcrypt passwords; per-user usage limits enforced at the router level.
- **RAG** — Qdrant vector store for document ingestion and semantic retrieval; embeddings via `sentence-transformers`.
- **Long-term memory** — per-user memory layer backed by Qdrant, surfaced to agents as context.
- **Stripe billing** — Pro and Enterprise price tiers; webhook handler for subscription lifecycle events.
- **Celery task queues** — separate queues per pipeline type (`linkedin_queue`, `blog_queue`, `gpu_queue`), all brokered by Redis.
- **Real-time streaming** — WebSocket connections poll SQLite `task_steps` written by Celery workers and push structured events to the dashboard.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Next.js 14 Dashboard (TailwindCSS + framer-motion)      │
│  WebSocket hooks  ←→  REST API                           │
└──────────────────────────┬───────────────────────────────┘
                           │ HTTP / WS
┌──────────────────────────▼───────────────────────────────┐
│  FastAPI (uvicorn)                                        │
│  ├── Routers: auth, linkedin, blog, instagram, rag,      │
│  │            memory, billing, runs, health, ws           │
│  ├── Middleware: CORS, rate limiting (slowapi)            │
│  └── Lifespan: SQLite init, settings load                 │
└──────────┬────────────────────────────┬──────────────────┘
           │ enqueue                    │ query
┌──────────▼────────┐        ┌──────────▼──────────────────┐
│  Redis (broker)   │        │  SQLite  (run / step store)  │
└──────────┬────────┘        └─────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│  Celery Workers                                          │
│  ├── linkedin_worker  (linkedin_queue, concurrency=4)   │
│  ├── blog_worker      (blog_queue,     concurrency=2)   │
│  ├── gpu_worker       (gpu_queue,      concurrency=1)   │
│  └── default worker   (celery queue,   concurrency=4)   │
│                                                         │
│  Agents (CrewAI + LangChain)                            │
│  LLM default: Ollama (local)                            │
│  Fallbacks:   NVIDIA NIM · Groq · OpenAI ·              │
│               Anthropic · Google Gemini                  │
└──────────────────────────────┬──────────────────────────┘
                               │
                    ┌──────────▼────────┐
                    │  ComfyUI (local)  │
                    │  host:8188        │
                    └───────────────────┘
```

**Vector store / RAG:** Qdrant Cloud (or self-hosted) for document embeddings and user memory.

---

## Project Structure

```
.
├── app/                              # FastAPI backend
│   ├── main.py                       # App factory, lifespan, router registration
│   ├── config.py                     # Pydantic Settings (env vars)
│   ├── routers/                      # HTTP + WebSocket route handlers
│   │   ├── auth.py
│   │   ├── linkedin.py               # REST + WS for LinkedIn pipeline
│   │   ├── blog.py                   # REST + WS for Blog pipeline
│   │   ├── instagram.py
│   │   ├── rag.py
│   │   ├── memory.py
│   │   ├── billing.py
│   │   ├── runs.py
│   │   └── ws.py
│   ├── services/
│   │   ├── linkedin_pipeline/        # hook_finder, post_writer, editor, qa_checker, approver
│   │   ├── blog_pipeline/            # researcher, writer, editor, qa_assembler, approver
│   │   ├── agents/                   # CrewAI agent + task definitions
│   │   ├── memory/                   # Memory manager
│   │   ├── rag/                      # Document processor + Qdrant store
│   │   ├── tools/                    # Custom CrewAI tools
│   │   ├── comfy_client.py           # ComfyUI HTTP client
│   │   └── style_guide.py
│   ├── tasks/                        # Celery task wrappers
│   │   ├── linkedin_task.py
│   │   └── blog_task.py
│   ├── celery_tasks/                 # Image + general pipeline tasks
│   │   ├── image_task.py
│   │   └── pipeline_task.py
│   ├── celery_app.py                 # Shared Celery instance
│   ├── core/                         # Auth deps, logging, shared clients
│   ├── db/                           # SQLite models, queries, Qdrant + Supabase helpers
│   ├── middleware/                   # Rate limiter
│   └── models/                       # Pydantic schemas
├── dashboard/                        # Next.js 14 frontend
│   └── src/
│       ├── app/                      # App Router pages
│       └── components/               # UI components
├── docker-compose.yml                # Full-stack compose (api, workers, redis, dashboard, flower)
├── Dockerfile                        # Backend image
├── requirements.txt                  # Python dependencies
├── start_comfy.sh                    # Helper to launch ComfyUI locally
└── CASE_STUDY.md                     # Architecture deep-dive
```

---

## Prerequisites

- Python 3.10+
- Node.js 18+ and npm
- Redis (or start via Docker Compose)
- An LLM: [Ollama](https://ollama.ai) running locally (default), **or** an API key for NVIDIA NIM / Groq / OpenAI / Anthropic / Google
- ComfyUI — optional, required only for image generation

---

## Setup

### Option A — Docker Compose (recommended)

```bash
cp app/.env.example app/.env   # fill in your keys
docker compose up -d
```

Services started: `redis`, `api`, `worker`, `linkedin_worker`, `blog_worker`, `gpu_worker`, `flower`, `dashboard`.

### Option B — Local development

**Backend**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create `app/.env`:
```env
DEFAULT_PROVIDER=ollama          # ollama | nvidia | groq | openai | anthropic | google
OLLAMA_MODEL=ollama/mistral:latest
OLLAMA_API_BASE=http://localhost:11434

# Optional API keys (only the provider you choose needs one)
NVIDIA_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

SECRET_KEY=change-me-to-64-random-chars
REDIS_URL=redis://localhost:6379/0

QDRANT_URL=
QDRANT_API_KEY=

STRIPE_SECRET_KEY=
STRIPE_WEBHOOK_SECRET=
STRIPE_PRO_PRICE_ID=
STRIPE_ENTERPRISE_PRICE_ID=
```

**Frontend**
```bash
cd dashboard
npm install
```

Create `dashboard/.env`:
```env
NEXT_PUBLIC_BACKEND_API=http://127.0.0.1:8000
```

---

## Running

**Terminal 1 — Backend API**
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 2 — Celery workers** (separate terminals or one per worker)
```bash
celery -A app.tasks:app worker -Q linkedin_queue --concurrency=4 --loglevel=info
celery -A app.tasks:app worker -Q blog_queue --concurrency=2 --loglevel=info
```

**Terminal 3 — Frontend**
```bash
cd dashboard && npm run dev
```

**Terminal 4 — Image generation (optional)**
```bash
./start_comfy.sh
```

---

## API Docs

Interactive docs available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
