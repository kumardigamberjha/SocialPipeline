# Wings of AI — Autonomous Content Pipeline & Analytics Hub

> A production-ready, multi-agent content generation engine and multi-platform analytics dashboard for developer content creators, DevRel teams, and tech brands. Research, generate, plan, schedule, and analyze content across **LinkedIn**, **YouTube**, and **Instagram** — with AI channel audits, strategy briefs, and multi-week content roadmaps for both YouTube and Instagram — powered by **FastAPI**, **Next.js 16**, **CrewAI**, and **Gemini** (3.6 Flash for text, Gemini Image for visuals).

For architectural deep dives and case study background, see [ARCHITECTURE.md](./ARCHITECTURE.md) and [CASE_STUDY.md](./CASE_STUDY.md).

---

## Table of Contents

- [Core Features](#core-features)
- [System Architecture](#system-architecture)
- [Project Directory Map](#project-directory-map)
- [Tech Stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Running the Services](#running-the-services)
- [Module Deep Dives](#module-deep-dives)
  - [Content Planner & Topic Library](#content-planner--topic-library)
  - [YouTube Analytics & Live Sync](#youtube-analytics--live-sync)
  - [Instagram Analytics & OAuth Engine](#instagram-analytics--oauth-engine)
  - [AI Content Roadmaps (Multi-Week / "30-Day" Planning)](#ai-content-roadmaps-multi-week--30-day-planning)
  - [Google Calendar Integration](#google-calendar-integration)
  - [Gemini Visual Synthesis Engine](#gemini-visual-synthesis-engine)
  - [Vector Memory & RAG System](#vector-memory--rag-system)
- [API Reference Overview](#api-reference-overview)
- [Environment Variables](#environment-variables)
- [Docker Compose Services](#docker-compose-services)
- [License & Contribution](#license--contribution)

---

## Core Features

### 🤖 Multi-Agent Generation Pipelines
| Pipeline | Orchestration | Queue & Concurrency | Output Artifacts |
|---|---|---|---|
| **LinkedIn Post** | Hook Finder → Post Writer → Editor → QA Checker → Approver | `linkedin_queue` (4) | Post copy, viral hooks, line breaks, hashtag cluster |
| **Blog Post** | Web Researcher → Section Writer → Editor → QA Assembler → Approver | `blog_queue` (2) | Technical markdown blog post with code blocks |
| **YouTube Script** | Topic Researcher → Script Writer → Editor → QA → SEO Specialist | `youtube_queue` (2) | Full video script, Shorts script, high-CTR titles, tags, thumbnail concepts |
| **Instagram Image** | Gemini image models (`gemini-3.1-flash-image` by default) | `gpu_queue` (1) | High-resolution post background image (4:5 ratio, 2K) |

### 📊 Multi-Platform Analytics & AI Insights
- **YouTube Analytics & Live Sync**:
  - Live video sync from **YouTube Data API v3** into `youtube_videos_live` (`POST /api/youtube-analytics/sync-live`), plus a separate real-metrics pull of impressions/CTR/average-view-% from the **YouTube Analytics API** (`POST /sync-analytics`).
  - Automated **nightly sync** via Celery Beat (12:05 AM IST) keeps live video data fresh without a manual trigger.
  - High-performance **Redis analytics caching layer** (5-minute TTL) in front of Postgres for all query endpoints.
  - **Gemini 3.6 Flash**-powered AI surface: full channel audit (`POST /ai-analysis`), per-playlist "what to make next" trending-topic suggestions grounded in live web search (`POST /playlist-trends`), a channel strategy brief (`POST /strategy`), a **1–8 week publishing roadmap** (`POST /roadmap`), and per-video growth recommendations — title/thumbnail/hook/tag fixes grounded in real stats + web trends (`POST /live-video/{id}/growth-recommendations`).
  - Local **Playlist Production Board** to track video ideas from idea → published (`/api/youtube-playlists`).
  - SEO title, tag count, and description word-count audit per video.
- **Instagram Analytics & Meta Graph API**:
  - Full **Meta OAuth 2.0** flow with automated **60-Day Long-Lived Token** exchange and runtime auto-refresh (auto-refreshes with <15 days remaining).
  - Three-tier read path — Redis cache → Postgres snapshot fallback → live Meta Graph API — plus **automated nightly refresh** via Celery Beat (12:10 AM IST) and a manual "Sync Now" (`POST /api/instagram-analytics/sync`).
  - Live profile metrics, total reach, impressions, link clicks, top posts/reels, and scored hashtag clusters.
  - **Gemini 3.6 Flash**-powered AI strategy briefs (`GET/POST /strategy`), **1–8 week content roadmaps** (`GET/POST /roadmap`), and AI-generated content-board ideas on demand (`POST /board/generate`), with a one-click bulk "add roadmap to board" action (`POST /roadmap/add-to-board`).
  - Interactive **Instagram Content Board** (Kanban) with status management (`idea`, `in_production`, `scheduled`, `published`).

### 📅 Content Operations & Scheduling
- **Editorial Planner**: Weekly and monthly editorial planning (`POST /api/plans`) with AI topic suggestions, deduplicated against all past published topics. A monthly plan is the closest analog to a "30-day content plan"; for a rolling AI-generated posting cadence, see the YouTube/Instagram **multi-week roadmap** generators above (1–8 weeks, commonly run at 4 weeks ≈ 30 days).
- **Production Status Lifecycle**: Multi-step video production tracker: `pending` → `script_generated` → `presentation_created` → `video_created` → `video_edited` → `video_published`.
- **Uncovered Topics Backlog**: Auto-research generates a batch of AI topic candidates per run; the first is used immediately and the rest are persisted as `uncovered` in the **Saved Topics** library instead of being discarded — deduplicated per user, surfaced via a dashboard banner and the `/topics` page, and generated on demand (`POST /api/saved-topics/{id}/generate`). Status flows `uncovered` → `generating` → `generated`.
- **Google Calendar Integration**: Fernet-encrypted OAuth token storage in Postgres; one-click event creation for approved content calendar items, auto-synced when a plan item's date changes.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       Next.js 16 Dashboard (React 19)                       │
│    Pages: Dashboard · Planner · Planner Analysis · Topics ·                 │
│           YouTube Analysis · Instagram Analysis                             │
│    Cookie-based auth (nx_at/nx_rt/nx_csrf) · TailwindCSS v4 ·               │
│    Framer Motion · Recharts · WebSockets                                    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / WS (CSRF double-submit)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                              FastAPI Backend                                │
│ ├── Routers: auth, linkedin, blog, youtube, instagram, instagram_analytics, │
│ │            instagram_auth, youtube_analytics, youtube_playlist_items,    │
│ │            planner, saved_topics, google_auth, rag, memory, billing,     │
│ │            runs, health, ws, generate                                     │
│ ├── Middleware: CORS, CSRF (ASGI), Rate Limiter (slowapi), Auth Deps        │
│ ├── Boot-time guard: every route must declare auth or be allowlisted        │
│ └── Services: Meta Graph API, YouTube Data/Analytics API, Gemini 3.6 Flash,  │
│               Gemini Image                                                  │
└──────────┬───────────────────────────┬──────────────────────────────────────┘
           │ enqueue                   │ query (asyncpg API / psycopg Celery)
┌──────────▼──────────────────┐   ┌────▼──────────────────────────────────────┐
│  Redis (2 instances)        │   │  PostgreSQL 16 (SQLAlchemy 2.0 + Alembic)  │
│  redis-cache  → analytics   │   │  Tables: agent_runs, task_steps,           │
│    cache, allkeys-lru       │   │  content_plans, saved_topics,              │
│  redis-broker → Celery      │   │  youtube_videos_live, instagram_board_     │
│    broker/results + auth    │   │  items, instagram_ai_reports,              │
│    denylist, AOF+noeviction │   │  youtube_analyses, oauth tokens, ...       │
└──────────┬───────────────────┘   └─────────────────────────────────────────┘
           │
┌──────────▼────────────────────────────────────────────────────────────────┐
│                           Celery Distributed Workers                        │
│ ├── worker            (celery/default queue, concurrency=4)                 │
│ ├── linkedin_worker   (linkedin_queue,       concurrency=4)                 │
│ ├── blog_worker       (blog_queue,           concurrency=2)                 │
│ └── gpu_worker        (gpu_queue,            concurrency=1)                 │
│ Celery Beat: youtube-nightly-sync (12:05 AM IST), instagram-nightly-refresh │
│              (12:10 AM IST)                                                 │
│                                                                             │
│ Agents: CrewAI + LangChain                                                  │
│ LLMs: Ollama (local) · NVIDIA NIM · Groq · OpenAI · Anthropic · Gemini      │
└──────────────────────────────┬──────────────────────────────┬───────────────┘
                               │                              │
                    ┌──────────▼────────────┐      ┌──────────▼────────────┐
                    │ Gemini Image API      │      │ Qdrant Vector DB      │
                    │ gemini-3.1-flash-image│      │ RAG + Agent Memory    │
                    └───────────────────────┘      └───────────────────────┘
```

> A one-shot `migrate` service (`alembic upgrade head`) runs before the API or any worker starts.

---

## Project Directory Map

```text
.
├── app/                                    # FastAPI Backend Root
│   ├── main.py                             # App factory, lifespan, CORS, CSRF, boot-time auth guard
│   ├── config.py                           # Pydantic Settings singleton (app/.env, Postgres/Redis/JWT)
│   ├── celery_app.py                       # Shared Celery instance, broker config & Beat schedule
│   ├── agents.py                           # Legacy 8-agent CrewAI roster
│   ├── crew.py                             # Legacy crew orchestration & LLM fallback logic
│   ├── task_factories.py                   # CrewAI task builders per platform
│   ├── llm.py                              # Multi-provider LLM factory (Ollama/NVIDIA/Groq/etc)
│   ├── schemas.py                          # Pydantic models for REST requests/responses
│   ├── ws_manager.py                       # WebSocket client manager for live streaming
│   │
│   ├── routers/                            # REST & WebSocket Route Handlers
│   │   ├── auth.py                         # Cookie/JWT register, login, refresh, OTP verify
│   │   ├── linkedin.py                     # LinkedIn post generation & WebSocket stream
│   │   ├── blog.py                         # Blog post generation & WebSocket stream
│   │   ├── youtube.py                      # YouTube script generation & WebSocket stream
│   │   ├── instagram.py                    # Gemini image generation endpoints & WS
│   │   ├── instagram_analytics.py          # Meta Graph API analytics, AI strategy/roadmap, content board
│   │   ├── instagram_auth.py               # Meta OAuth flow & 60-day token lifecycle
│   │   ├── youtube_analytics.py            # YouTube Data/Analytics API, AI analysis suite, live sync
│   │   ├── youtube_playlist_items.py       # Playlist production board management
│   │   ├── planner.py                      # Content plan CRUD & AI topic suggestions
│   │   ├── saved_topics.py                 # Uncovered Topics backlog CRUD & promotion
│   │   ├── google_auth.py                  # Google Calendar OAuth & event creation
│   │   ├── rag.py                          # Qdrant document ingestion & search
│   │   ├── memory.py                       # Per-user agent vector memory
│   │   ├── billing.py                      # Stripe subscription webhooks & checkout
│   │   ├── runs.py                         # Pipeline run history telemetry
│   │   ├── ws.py                           # Generic WebSocket streaming
│   │   ├── generate.py                     # Legacy direct generation endpoint
│   │   └── health.py                       # Health check endpoint
│   │
│   ├── services/                           # External API clients & Business Logic
│   │   ├── instagram_auth.py               # OAuth URL builder, code exchange, token auto-refresh
│   │   ├── instagram_data.py               # Meta Graph API live profile, posts & hashtag scoring
│   │   ├── instagram_cache.py              # Redis→Postgres snapshot caching for analytics reads
│   │   ├── instagram_ai_analysis.py        # Gemini strategy brief / roadmap / board-idea generation
│   │   ├── youtube_data.py                 # YouTube Data API v3 client helpers
│   │   ├── youtube_sync_service.py         # Live video + real Analytics-API sync
│   │   ├── youtube_ai_analysis.py          # Gemini channel audit / trends / strategy / roadmap / growth recs
│   │   ├── youtube_import.py               # CSV historical analytics importer
│   │   ├── plan_service.py                 # Content plan reconciliation & generation dispatch
│   │   ├── topic_suggester.py              # AI topic deduplication & suggestion engine
│   │   ├── saved_topic_service.py          # Uncovered Topics backlog persistence & reconciliation
│   │   ├── roadmap_to_plan.py              # AI roadmap → structured plan item converter
│   │   ├── dispatch.py                     # Task dispatch (Celery or BackgroundTask fallback)
│   │   ├── gemini_image_client.py          # Gemini image API client & prompt builder
│   │   ├── comfy_client.py                 # RETIRED ComfyUI client (kept commented out)
│   │   ├── google_calendar.py              # Google Calendar OAuth & event creator
│   │   ├── style_guide.py                  # Brand voice & style guide manager
│   │   └── usage.py                        # Rate limit & usage tracking
│   │
│   ├── tasks/ + celery_tasks/               # Celery task bodies (generation pipelines + nightly syncs)
│   ├── core/                               # Auth primitives: cookies, CSRF, JWT tokens, OTP,
│   │                                        #   email (SMTP), Redis client, auth dependencies
│   ├── db/                                 # Database Schema, Sessions, Queries & Helpers
│   │   ├── base.py                         # SQLAlchemy declarative base & naming conventions
│   │   ├── tables.py                       # ORM schema — 25+ tables, no relationship() mappings
│   │   ├── session.py / sync_session.py    # Async (API/asyncpg) vs sync (Celery/psycopg) engines
│   │   ├── queries.py / sync_queries.py    # Hand-written select() queries (async / sync)
│   │   ├── content_tracker.py              # Legacy standalone SQLite dedup tracker (pre-Postgres)
│   │   └── qdrant.py                       # Qdrant vector store connection
│   └── middleware/                         # Middleware (slowapi rate limiting)
│
├── alembic/versions/                       # Linear DB migrations (initial schema, Instagram board,
│                                            #   Instagram AI reports, YouTube analytics fields)
│
├── dashboard/                              # Next.js 16 Frontend Root
│   ├── src/
│   │   ├── app/                            # Next.js App Router pages
│   │   │   ├── (dashboard)/                # Content Generation Hub + analysis route group
│   │   │   │   ├── planner-analysis/       # Planner analytics dashboard page
│   │   │   │   ├── youtube-analysis/       # YouTube Analytics & AI insights page
│   │   │   │   └── instagram-analysis/     # Instagram Analytics & AI insights page
│   │   │   ├── planner/                    # Editorial Content Planner page
│   │   │   └── topics/                     # Saved Topics / Uncovered Topics backlog page
│   │   ├── components/                     # Modular React Components
│   │   │   ├── AgentPipeline.tsx           # Live agent pipeline progress monitor
│   │   │   ├── ApprovalQueue.tsx           # Interactive content review & approval UI
│   │   │   ├── Header.tsx                  # System metrics & health status bar
│   │   │   ├── TelemetryLedger.tsx         # Telemetry run history table
│   │   │   ├── planner/                    # Planner lists, detail cards, status dropdowns
│   │   │   ├── instagram/                  # Instagram analytics dashboard, board & AI panels
│   │   │   ├── youtube/                    # YouTube analytics dashboard, playlist board & AI panels
│   │   │   └── topics/                     # Saved topics list & Uncovered Topics banner
│   │   └── lib/                            # API client abstractions
│   │       ├── api.ts                      # Core REST client (CSRF + refresh handling)
│   │       ├── plannerApi.ts               # Content planner API client
│   │       ├── savedTopicsApi.ts           # Saved topics API client
│   │       └── youtubePlaylistItemsApi.ts  # Playlist board API client
│
├── data/                                   # Local data directory (CSV imports, legacy tracker DB)
├── generated_posts/                        # Generated image output directory
├── docker-compose.yml                      # Docker Compose orchestration (Postgres, dual Redis, workers)
├── Dockerfile                              # Python container spec
├── requirements.txt                        # Python dependencies
├── start_comfy.sh                          # RETIRED ComfyUI launch helper (no-op)
├── CASE_STUDY.md                           # System design & business case study
└── ARCHITECTURE.md                         # Technical architecture deep dive (data model, auth, trade-offs)
```

---

## Tech Stack

| Component | Technology | Description |
|---|---|---|
| **Backend Framework** | FastAPI + Uvicorn | High-performance Python async REST & WebSockets |
| **Agent Framework** | CrewAI + LangChain | Multi-agent orchestration syndicate |
| **Primary LLMs** | Ollama (Local) · Gemini 3.6 Flash | Fast local inference & cloud AI video analysis |
| **LLM Providers** | NVIDIA NIM · Groq · OpenAI · Anthropic | Multi-tenant LLM provider fallback strategy |
| **Task Queue & Broker** | Celery 5 + Redis 7 (2 instances) | `redis-broker` (broker/results + auth denylist, AOF) is kept separate from `redis-cache` (analytics cache, evictable) |
| **Relational Database** | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic | Async (`asyncpg`) engine for the API, sync (`psycopg`) engine for Celery; schema-versioned migrations |
| **Auth & Sessions** | Custom cookie/JWT system (`app/core/*`) | HttpOnly access/refresh cookies, CSRF double-submit, Redis revocation denylist, email OTP verification — no third-party auth provider |
| **Vector Storage** | Qdrant Cloud / OSS | Vector embeddings for RAG & agent memory |
| **Image Generation** | Gemini Image (`gemini-3.1-flash-image`) | Hosted 4:5 post-visual synthesis — no local GPU required |
| **External APIs** | Meta Graph API · YouTube Data & Analytics API v3 · Google Calendar API | Social media analytics & calendar sync |
| **Frontend Stack** | Next.js 16 + React 19 + TypeScript | Glassmorphic, responsive web dashboard |
| **Styling & Motion** | Vanilla CSS + TailwindCSS v4 + Framer Motion | Modern dark mode aesthetic with micro-interactions |

---

## Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18.x or higher with `npm`
- **PostgreSQL**: 16.x (running locally or via Docker Compose)
- **Redis**: 7.x, two instances — cache + broker/state (or let Docker Compose provision both)
- **LLM Engine**: [Ollama](https://ollama.ai) running locally *(default)* or an API key for NVIDIA NIM, Groq, OpenAI, Anthropic, or Google Gemini.
- **Gemini API key**: Required for Instagram image generation (`GEMINI_API_KEY`). No local GPU or ComfyUI install is needed any more.

---

## Setup & Installation

### Option A — Docker Compose *(Recommended)*

```bash
# 1. Clone the repository
git clone https://github.com/kumardigamberjha/SocialPipeline.git
cd SocialPipeline

# 2. Copy and configure backend environment file
cp app/.env.example app/.env

# 3. Start all microservices in background
docker compose up -d
```

### Option B — Local Manual Setup

#### 1. Backend Setup
```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create app environment file
cp app/.env.example app/.env
# Set DATABASE_URL to a Postgres 16 instance, e.g.:
# DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus

# Apply database migrations
alembic upgrade head
```

#### 2. Frontend Setup
```bash
cd dashboard
npm install

# Create frontend environment file
echo "NEXT_PUBLIC_BACKEND_API=http://127.0.0.1:8000" > .env
```

---

## Running the Services

### 1. Database Migrations
```bash
# Apply all pending Alembic migrations before starting the API
alembic upgrade head
```

### 2. Backend API
```bash
# Start FastAPI backend on port 8000
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Celery Workers
```bash
# Default queue worker (matches docker-compose's `worker` service):
celery -A app.celery_app worker -Q celery --concurrency=4 --loglevel=info

# Dedicated worker queues (matches docker-compose exactly):
celery -A app.tasks:app worker -Q linkedin_queue --concurrency=4 --loglevel=info
celery -A app.tasks:app worker -Q blog_queue --concurrency=2 --loglevel=info
celery -A app.celery_app worker -Q gpu_queue --concurrency=1 --loglevel=info

# YouTube script generation dispatches to `youtube_queue` (app/services/dispatch.py) —
# no dedicated compose service consumes it yet, so for local dev either add it to an
# existing worker's -Q list or run a standalone one:
celery -A app.tasks:app worker -Q youtube_queue --concurrency=2 --loglevel=info
```
> *Note: If Redis is unavailable, pipelines gracefully default to FastAPI `BackgroundTasks` in development only — this fallback is refused when `ENVIRONMENT=production`.*

### 4. Frontend Dashboard
```bash
cd dashboard
npm run dev
# Dashboard accessible at http://localhost:3000
```

### 5. Celery Flower Inspector (Monitoring)
```bash
celery -A app.celery_app flower --port=5555
# Dashboard accessible at http://localhost:5555
```

---

## Module Deep Dives

### Content Planner & Topic Library
- **AI Topic Suggestions**: `POST /api/plans/suggest-topics` uses an LLM (primed with a "do-not-repeat" list built from content history, recent plan items, and real synced YouTube/Instagram content) to suggest tailored topics for a `weekly` (7 topics) or `monthly` (12 topics) plan. Duplicate topics are filtered against `content_tracker`; if too many suggestions are dropped as duplicates, one automatic replacement round is issued. Publish dates are assigned deterministically in code, never by the LLM.
- **Plan Lifecycle**: `POST /api/plans` creates a plan and computes its `end_date`; items are tracked, edited, and reviewed via `/api/plans/{id}/items/*`, with generation dispatched per item (`POST /items/{id}/generate`) to the LinkedIn/Blog/YouTube pipelines.
- **Production Status Tracking**: Track items through 6 distinct stages (`pending` → `script_generated` → `presentation_created` → `video_created` → `video_edited` → `video_published`).
- **Uncovered Topics Backlog**: When auto-research generates a batch of candidate topics, only the first is used immediately — the rest are saved as `uncovered` in the Saved Topics library (`/api/saved-topics`) instead of being thrown away, deduplicated per user, and surfaced via a dashboard banner plus the `/topics` page. Each can be generated on demand (`POST /{id}/generate`) or dismissed; status flows `uncovered` → `generating` → `generated` (or back to `uncovered` if generation fails).
- **Planner Analytics**: The `/planner-analysis` dashboard page (backed by `GET /api/plans/stats`) surfaces aggregate planning metrics across all plans.

### YouTube Analytics & Live Sync
- **Data Sync**: `POST /api/youtube-analytics/sync-live` fetches all channel uploads via the YouTube Data API v3 (title, tags, duration, views, likes, comments, SEO score) into `youtube_videos_live`; `POST /sync-analytics` separately pulls real impressions, CTR, and average-view-% from the YouTube **Analytics** API. Both also run automatically every night at 12:05 AM IST via Celery Beat. A legacy CSV import path (`POST /import`) covers historical Studio exports.
- **Redis Caching**: Query endpoints are cached in `redis-cache` (5-minute TTL) in front of Postgres to keep dashboard reads fast.
- **Gemini 3.6 Flash AI Suite**:
  - `POST /ai-analysis` — full channel performance audit.
  - `POST /playlist-trends` — per-playlist "what to make next" suggestions, grounded in live web search.
  - `POST /strategy` — channel-wide strategy brief (what's working, gaps, priorities).
  - `POST /roadmap` — a configurable **1–8 week publishing roadmap** with dated, titled video ideas.
  - `POST /live-video/{video_id}/growth-recommendations` — per-video title/thumbnail/hook/tag fixes grounded in that video's real stats plus current web trends.
  - All AI runs are persisted (`GET /analyses`, `GET /analyses/latest`) so they don't need to be regenerated on every page load.
- **Playlist Production Board**: Local idea → published tracker for planned videos (`/api/youtube-playlists`), independent of real YouTube playlist writes.

### Instagram Analytics & OAuth Engine
- **Meta OAuth 2.0 Flow**: Users initiate authentication via `GET /api/instagram-auth/url`. Upon approval, Meta redirects to `GET /api/instagram/oauth/callback`, which exchanges the authorization code for a short-lived token, converts it into a **60-day long-lived token**, and stores it Fernet-encrypted in Postgres (`instagram_oauth_tokens`).
- **Token Health Check**: `refresh_if_needed()` auto-refreshes the token whenever fewer than 15 days remain (or on demand via `POST /api/instagram-auth/refresh`); `GET /status` reports connection/expiry health.
- **Three-Tier Data Path**: Analytics reads hit `redis-cache` first, fall back to a pruned Postgres snapshot (`instagram_snapshots`, last 7 rows/user) if the cache is cold, and only hit the live Meta Graph API on an explicit `POST /api/instagram-analytics/sync` or the nightly Celery Beat refresh (12:10 AM IST).
- **Gemini 3.6 Flash AI Suite**: `GET/POST /strategy` (strategy brief), `GET/POST /roadmap` (**1–8 week content roadmap**), and `POST /board/generate` (AI-generated new "idea" board items) — all grounded in real synced profile/post/hashtag data and persisted to `instagram_ai_reports`.
- **Content Board**: Kanban board (`GET/POST/PUT/DELETE /board`) across `idea` → `in_production` → `scheduled` → `published`, with image-prompt history, scheduled publish dates, and a one-click **"add roadmap to board"** bulk action (`POST /roadmap/add-to-board`).

### AI Content Roadmaps (Multi-Week / "30-Day" Planning)
Both analytics modules share the same roadmap pattern: a Gemini-backed generator takes the account's real synced performance data and produces a dated, week-numbered publishing plan for a caller-chosen window of **1 to 8 weeks** (`POST /api/youtube-analytics/roadmap`, `POST /api/instagram-analytics/roadmap`). There is no separate "30-day plan" endpoint by that name — a 4-week roadmap is the practical equivalent, and roadmap items can be pushed onto each platform's production board (or, for the Content Planner, created as a `monthly` plan via `POST /api/plans`) for day-by-day scheduling.

### Google Calendar Integration
- **OAuth Setup**: Connect Google Calendar via `GET /api/google/authorize`. Tokens are encrypted using Fernet cryptography (`TOKEN_ENCRYPTION_KEY`, shared with Instagram) before Postgres persistence (`google_oauth_tokens`).
- **Event Scheduling**: One-click event creation for approved content items, creating calendar entries with 1-day and 1-hour reminders, auto-synced when a plan item's date changes.

---

## API Reference Overview

When running in development (`ENVIRONMENT=development`), interactive documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

For the complete plain-text API documentation detailing all endpoints, request schemas, and response formats, refer to [api_documentation.txt](./api_documentation.txt).

---

## Environment Variables

Key backend environment variables configured in `app/.env`:

```env
# ── System Environment ────────────────────────────
ENVIRONMENT=development                # development | production
LOG_LEVEL=INFO

# ── LLM Provider Configuration ────────────────────
DEFAULT_PROVIDER=ollama                # ollama | nvidia | groq | openai | anthropic | google
OLLAMA_MODEL=gemma4:31b-cloud
OLLAMA_API_BASE=http://localhost:11434
ANALYSIS_MODEL=gemini/gemini-3.6-flash

# ── LLM API Keys ──────────────────────────────────
NVIDIA_API_KEY=
GROQ_API_KEY=
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=

# ── Database (PostgreSQL 16) ──────────────────────
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ── Auth / Sessions ────────────────────────────────
SECRET_KEY=generate-a-random-64-char-string-for-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_SECONDS=900            # 15 minutes
REFRESH_TOKEN_TTL_SECONDS=2592000       # 30 days, absolute

# ── Redis (2 instances — cache vs. broker/state) ──
REDIS_CACHE_URL=redis://localhost:6379/0     # analytics/AI response cache
REDIS_STATE_URL=redis://localhost:6380/2     # auth denylist, WS tickets
CELERY_BROKER_URL=redis://localhost:6380/0
CELERY_RESULT_BACKEND=redis://localhost:6380/1

# ── Email / SMTP (OTP verification) ───────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=                              # e.g. you@gmail.com
SMTP_PASSWORD=                          # Gmail App Password, not your account password

# ── Meta Instagram Graph API ─────────────────────
INSTAGRAM_APP_ID=
INSTAGRAM_APP_SECRET=
INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/instagram/oauth/callback

# ── Google Calendar OAuth ─────────────────────────
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google/callback

# ── Token Encryption (Google + Instagram, shared) ─
TOKEN_ENCRYPTION_KEY=                   # Fernet key; GOOGLE_TOKEN_ENCRYPTION_KEY still works as an alias

# ── Image Generation (Gemini) ─────────────────────
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image   # or gemini-3.1-flash-lite-image / gemini-3-pro-image
GEMINI_IMAGE_ASPECT_RATIO=4:5
GEMINI_IMAGE_SIZE=2K                        # 512 | 1K | 2K | 4K
IMAGE_OUTPUT_DIR=                           # defaults to dashboard/public/generated_posts
                                            # (COMFY_OUTPUT_DIR still works as an alias)

# ── ComfyUI Engine (retired — kept for reference) ──
# COMFY_HOST=127.0.0.1
# COMFY_PORT=8188
```

---

## Docker Compose Services

| Service Name | Container Port | Host Port | Purpose |
|---|---|---|---|
| `postgres` | `5432` | `127.0.0.1:5433` | PostgreSQL 16 primary database |
| `redis-broker` | `6379` | `127.0.0.1:6380` | Celery broker/results + auth denylist (AOF, `noeviction`) |
| `redis-cache` | `6379` | `127.0.0.1:6379` | Analytics/AI response cache (`allkeys-lru`, evictable) |
| `migrate` | — | — | One-shot Alembic migration runner, completes before `api`/workers start |
| `api` | `8000` | `0.0.0.0:8000` | FastAPI backend application |
| `worker` | — | — | Default Celery worker queue (`celery`, concurrency 4) |
| `linkedin_worker` | — | — | Dedicated LinkedIn generation worker |
| `blog_worker` | — | — | Dedicated Blog post worker |
| `gpu_worker` | — | — | Image pipeline worker (Gemini image renders) |
| `flower` | `5555` | `127.0.0.1:5555` | Celery task monitoring tool (loopback-only; set `FLOWER_BASIC_AUTH`) |
| `dashboard` | `3000` | `0.0.0.0:3000` | Next.js frontend web dashboard |

---

## License & Contribution

Built for the **MyEmpire** content ecosystem — powering developer content creation for [@codingindiaai](https://instagram.com/codingindiaai).

1. Fork the repository & create a feature branch (`git checkout -b feature/amazing-feature`).
2. Commit your changes with standard conventional commits (`git commit -m 'feat: add amazing feature'`).
3. Push to your origin branch (`git push origin feature/amazing-feature`).
4. Open a Pull Request for review.
