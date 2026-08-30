# 🦅 Wings of AI (Nexus) — Autonomous Content Pipeline & Analytics Hub

<div align="center">

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16.0+-black.svg?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7.0-DC382D.svg?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io)
[![Celery](https://img.shields.io/badge/Celery-5.4-37814A.svg?style=for-the-badge&logo=celery&logoColor=white)](https://docs.celeryq.dev)
[![Gemini](https://img.shields.io/badge/Google%20Gemini-3.6%20Flash%20%7C%20Image-4285F4.svg?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com)

**A production-grade, multi-agent content generation engine, AI assistant, competitor intelligence platform, and multi-platform analytics hub for developer content creators, DevRel teams, and digital media brands.**

*Powers high-velocity content creation for [@codingindiaai](https://instagram.com/codingindiaai).*

[Key Features](#-key-features) • [Architecture](#-system-architecture) • [Dashboard Modules](#-dashboard-modules) • [Quickstart](#-setup--installation) • [API Guide](#-api-reference-overview) • [Campaign & Media Suite](#-marketing-campaign--media-suite)

</div>

---

## 📖 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [System Architecture](#-system-architecture)
- [Project Directory Map](#-project-directory-map)
- [Tech Stack](#-tech-stack)
- [Dashboard Modules](#-dashboard-modules)
  - [1. Nexus Command Center (`/`)](#1-nexus-command-center-)
  - [2. AI Schedule & Strategy Assistant (`/assistant`)](#2-ai-schedule--strategy-assistant-assistant)
  - [3. Topics Backlog & Uncovered Topics Vault (`/topics`)](#3-topics-backlog--uncovered-topics-vault-topics)
  - [4. Cross-Platform Editorial Planner (`/planner`)](#4-cross-platform-editorial-planner-planner)
  - [5. Gemini Image Studio (`/image-studio`)](#5-gemini-image-studio-image-studio)
  - [6. YouTube Analytics & Competitor Outlier Engine (`/youtube-analysis`)](#6-youtube-analytics--competitor-outlier-engine-youtube-analysis)
  - [7. Instagram Analytics, Meta Graph & Kanban Board (`/instagram-analysis`)](#7-instagram-analytics-meta-graph--kanban-board-instagram-analysis)
  - [8. Personal Intelligence Engine (`/personal-intelligence`)](#8-personal-intelligence-engine-personal-intelligence)
- [Multi-Agent Generation Pipelines](#-multi-agent-generation-pipelines)
- [Prerequisites](#-prerequisites)
- [Setup & Installation](#-setup--installation)
  - [Option A — Docker Compose (Recommended)](#option-a--docker-compose-recommended)
  - [Option B — Local Manual Setup](#option-b--local-manual-setup)
- [Running the Services](#-running-the-services)
- [Environment Configuration](#-environment-configuration)
- [Docker Compose Services](#-docker-compose-services)
- [Model Context Protocol (MCP) Support](#-model-context-protocol-mcp-support)
- [Marketing Campaign & Media Suite](#-marketing-campaign--media-suite)
- [Security & Authentication Model](#-security--authentication-model)
- [License & Contribution](#-license--contribution)

---

## 🌟 Overview

**Wings of AI (Nexus / SocialPipeline)** is a complete operating system for digital creators and enterprise DevRel teams. It eliminates writer's block, automates research, synthesizes visual assets, plans publishing schedules across calendar networks, tracks competitor breakout trends, and provides deep AI-grounded insights directly from real **YouTube** and **Instagram** performance data.

```
Research Trends ──► Deduplicate Topics ──► Multi-Agent Pipeline ──► Gemini Visuals ──► Calendar Sync ──► Live Analytics
       ▲                                                                                                    │
       └────────────────────────── Personal Intelligence & Feedback Loop ───────────────────────────────────┘
```

---

## ⚡ Key Features

### 🤖 Autonomous Multi-Agent Pipelines
- **LinkedIn Posts**: 5-stage syndicate (Hook Finder → Post Writer → Editor → QA Checker → Approver) delivering high-engagement formatting and hashtag clustering.
- **Technical Blog Posts**: Comprehensive research and multi-section authoring loop with code block verification and markdown assembly.
- **YouTube Scripts & Shorts**: Hook generation, full-length timestamped video scripts, viral Shorts concepts, SEO titles, and thumbnail directives.
- **Gemini Visual Synthesis**: Native high-resolution post graphics (4:5 portrait, 1:1, 16:9) powered by Google Gemini Image models (`gemini-3.1-flash-image`, `gemini-3-pro-image`).

### 🎯 Competitor Intelligence & Outlier Detection
- **AI Competitor Discovery**: Automated discovery of niche YouTube competitors verified against the YouTube Data API.
- **Breakout & Outlier Analysis**: Identifies competitor videos performing significantly above channel baselines (high CTR & velocity) to inspire fresh content angles.
- **Generator Context Injection**: Injects top competitor hooks and breakout themes directly into topic suggestions and script generators.

### 🧠 Personal Intelligence & Custom Directives
- **Global & Scoped Rules**: Define voice, tone, formatting constraints, taboo topics, and brand rules injected into all agent generation prompts.
- **Dynamic Goal Tracking**: Track milestone goals (subscriber counts, views, reach targets) continuously calibrated against synced live platform analytics.

### 💬 AI Command Assistant (`/assistant`)
- **Centralized Copilot**: Interactive AI assistant with complete context over your editorial calendar, topic backlog, and platform performance.
- **Action Execution Protocol**: Proposes actionable database mutations (e.g., creating plan items, scheduling dates, generating content) with instant 1-click user confirmation or cancellation.
- **Zero-Latency Daily Digest**: Instant summaries of pending tasks and scheduled posts for today without consuming LLM generation quota.

### 📊 Deep Multi-Platform Analytics
- **YouTube Data & Analytics API v3**: Live sync of uploads, views, watch time, impressions, CTR, audience retention, and SEO tag audits, backed by automated Celery Beat nightly syncs (12:05 AM IST).
- **Meta Instagram Graph API**: 60-day Long-Lived Token lifecycle with automatic background refresh (<15 days remaining), reach/impressions tracking, top reels analysis, and hashtag scoring.
- **Gemini 3.6 Flash Strategic Audits**: Channel audits, 1–8 week publishing roadmaps, per-playlist web trends, and per-video growth fixes.

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Next.js 16 Dashboard (React 19)                        │
│  Pages: Nexus Hub (/) · Assistant (/assistant) · Topics Backlog (/topics) · │
│         Planner (/planner) · Image Studio (/image-studio) ·                 │
│         YouTube Analysis (/youtube-analysis) · Instagram (/instagram) ·     │
│         Personal Intelligence (/personal-intelligence)                      │
│  Stack: Cookie Auth (nx_at/nx_rt) · CSRF Protection · Tailwind CSS v4 ·     │
│         Framer Motion · Lucide Icons · Recharts · WebSockets                │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ HTTP / WebSockets (CSRF double-submit)
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                              FastAPI Backend                                │
│ ├── Routers: auth, assistant, personal_intelligence, images, linkedin,      │
│ │            blog, youtube, youtube_analytics, youtube_competitors,        │
│ │            youtube_playlist_items, instagram, instagram_analytics,       │
│ │            instagram_auth, planner, saved_topics, google_auth, rag,       │
│ │            memory, billing, runs, health, ws                              │
│ ├── Middleware: Rate Limiting (SlowAPI), CORS, CSRF, Boot-time Auth Guard   │
│ └── Services: Meta Graph API, YouTube API v3, Google Calendar, Gemini 3.6,  │
│               Gemini Image Client, Personal Intelligence Directives         │
└──────────┬───────────────────────────┬──────────────────────────────────────┘
           │ Enqueue Tasks             │ Queries (asyncpg / psycopg)
┌──────────▼──────────────────┐   ┌────▼──────────────────────────────────────┐
│  Redis Broker (6380)        │   │  PostgreSQL 16 (SQLAlchemy 2.0 + Alembic)  │
│  - Celery Broker (db 0)     │   │  - 25+ relational tables                  │
│  - Celery Results (db 1)    │   │  - Agent runs, task steps, content plans  │
│  - Auth Denylist & WS (db 2)│   │  - YouTube videos & competitor data       │
│  - Append-Only / noeviction │   │  - Instagram board, rules, user goals     │
└──────────┬──────────────────┘   └───────────────────────────────────────────┘
           │
┌──────────▼──────────────────┐   ┌───────────────────────────────────────────┐
│  Redis Cache (6379)         │   │  Qdrant Vector Database                   │
│  - Analytics Cache (5m TTL) │   │  - RAG document embeddings                │
│  - LLM Response Cache       │   │  - Per-user agent long-term memory        │
│  - allkeys-lru (evictable)  │   └───────────────────────────────────────────┘
└──────────┬──────────────────┘
           │
┌──────────▼──────────────────────────────────────────────────────────────────┐
│                         Distributed Celery Workers                          │
│ ├── default_worker    (celery queue,          concurrency=4)                │
│ ├── linkedin_worker   (linkedin_queue,        concurrency=4)                │
│ ├── blog_worker       (blog_queue,            concurrency=2)                │
│ ├── gpu_worker        (gpu_queue,             concurrency=1)                │
│ └── youtube_worker    (youtube_queue,         concurrency=2)                │
│                                                                             │
│ Celery Beat Cron Schedules:                                                 │
│  - 12:05 AM IST : Nightly YouTube Live Sync & Analytics                     │
│  - 12:10 AM IST : Nightly Instagram Graph API Refresh                       │
│  - Sunday 2:00 AM IST : YouTube Competitor Weekly Batch Sync                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Directory Map

```text
.
├── app/                                    # FastAPI Backend Root
│   ├── main.py                             # App factory, lifespan, CORS, CSRF, boot-time auth guard
│   ├── config.py                           # Pydantic Settings singleton (app/.env)
│   ├── celery_app.py                       # Shared Celery instance, broker config & Beat schedule
│   ├── schemas.py                          # Pydantic models for REST requests/responses
│   ├── llm.py                              # Multi-provider LLM factory (Gemini, NVIDIA, Ollama, Groq)
│   ├── ws_manager.py                       # WebSocket client manager for live progress streaming
│   │
│   ├── routers/                            # REST & WebSocket Route Handlers (25+ modules)
│   │   ├── assistant.py                    # Centralized AI Assistant (/ask, actions confirm/cancel, digest)
│   │   ├── personal_intelligence.py        # Rules & Directives engine, dynamic goal tracking
│   │   ├── images.py                       # Gemini Image Studio generation & authenticated streaming
│   │   ├── auth.py                         # Cookie/JWT register, login, refresh, OTP verify
│   │   ├── linkedin.py                     # LinkedIn multi-agent generation & WebSocket stream
│   │   ├── blog.py                         # Technical blog generation & WebSocket stream
│   │   ├── youtube.py                      # YouTube video/Shorts script generation & WebSocket stream
│   │   ├── youtube_analytics.py            # YouTube Data/Analytics API, AI audit, roadmaps, growth recs
│   │   ├── youtube_competitors.py          # AI competitor discovery, outlier tracking & sync
│   │   ├── youtube_playlist_items.py       # Playlist production board management
│   │   ├── instagram.py                    # Instagram generation endpoints & WebSocket stream
│   │   ├── instagram_analytics.py          # Meta Graph API analytics, AI strategy/roadmap, Kanban board
│   │   ├── instagram_auth.py               # Meta OAuth flow & 60-day token lifecycle
│   │   ├── planner.py                      # Content plan CRUD, 6-stage lifecycle, AI topic suggester
│   │   ├── saved_topics.py                 # Uncovered Topics backlog CRUD & 1-click promotion
│   │   ├── google_auth.py                  # Google Calendar OAuth & 2-way event creation
│   │   ├── rag.py                          # Qdrant document ingestion & vector search
│   │   ├── memory.py                       # Per-user agent vector memory
│   │   ├── billing.py                      # Stripe subscription webhooks & checkout
│   │   ├── runs.py                         # Pipeline run telemetry ledger
│   │   ├── ws.py                           # Real-time WebSocket streaming
│   │   └── health.py                       # Service health check endpoint
│   │
│   ├── services/                           # Business Logic & External API Integrations
│   │   ├── assistant.py                    # AI Assistant conversation & action proposal engine
│   │   ├── personal_intelligence.py        # Rules builder, token budgeter & prompt injector
│   │   ├── goal_service.py                 # Goal tracker calibrated against synced platform stats
│   │   ├── youtube_competitor.py           # Competitor discovery & outlier video analysis
│   │   ├── youtube_sync_service.py         # Live video uploads & real Analytics API sync
│   │   ├── youtube_ai_analysis.py          # Gemini channel audit / trends / strategy / roadmap
│   │   ├── instagram_data.py               # Meta Graph API live profile, posts & hashtag scoring
│   │   ├── instagram_cache.py              # Redis→Postgres snapshot caching for analytics reads
│   │   ├── instagram_ai_analysis.py        # Gemini Instagram strategy brief / roadmap / board ideas
│   │   ├── gemini_image_client.py          # Google Gemini Image generation client
│   │   ├── google_calendar.py              # Google Calendar OAuth & event creator
│   │   ├── plan_service.py                 # Content plan reconciliation & generation dispatch
│   │   └── topic_suggester.py              # AI topic deduplication & suggestion engine
│   │
│   ├── core/                               # Security Primitives: Cookies, CSRF, JWT, OTP, Fernet, Redis
│   ├── db/                                 # SQLAlchemy 2.0 Async/Sync Sessions, Queries & Models
│   │   ├── tables.py                       # 25+ Relational Database Tables
│   │   ├── session.py / sync_session.py    # Async (asyncpg) vs Sync (psycopg) database engines
│   │   └── queries.py / sync_queries.py    # Type-safe SQLAlchemy query helpers
│   └── middleware/                         # SlowAPI rate limiters & request interceptors
│
├── dashboard/                              # Next.js 16 (React 19) Frontend Application
│   ├── src/
│   │   ├── app/                            # App Router Pages
│   │   │   ├── (auth)/                     # Login, Register, Verify OTP, Reset Password
│   │   │   └── (dashboard)/                # Protected App Shell
│   │   │       ├── page.tsx                # Nexus Command Center (/)
│   │   │       ├── assistant/              # AI Assistant & Daily Digest (/assistant)
│   │   │       ├── topics/                 # Uncovered Topics Backlog (/topics)
│   │   │       ├── planner/                # Cross-Platform Editorial Calendar (/planner)
│   │   │       ├── planner-analysis/       # Aggregate Planning Analytics (/planner-analysis)
│   │   │       ├── image-studio/           # Gemini Prompt-to-Image Studio (/image-studio)
│   │   │       ├── youtube-analysis/       # YouTube Live Stats, AI Suite & Competitors
│   │   │       ├── instagram-analysis/     # Instagram Insights, Strategy & Kanban Board
│   │   │       └── personal-intelligence/  # Rules, Directives & Goal Tracker
│   │   ├── components/                     # Reusable UI & Platform Components
│   │   │   ├── Sidebar.tsx                 # Dynamic collapsible navigation
│   │   │   ├── Header.tsx                  # Live system status, metrics & quota tracker
│   │   │   ├── AgentPipeline.tsx           # Real-time multi-agent execution monitor
│   │   │   ├── ApprovalQueue.tsx           # Interactive content review & approval interface
│   │   │   ├── TelemetryLedger.tsx         # Telemetry execution history table
│   │   │   ├── assistant/                  # Assistant chat interface & action cards
│   │   │   ├── youtube/                    # YouTube analytics cards, audit panels & competitor hub
│   │   │   ├── instagram/                  # Instagram analytics cards, AI panels & Kanban board
│   │   │   ├── planner/                    # Calendar views, detail modals & status badges
│   │   │   └── topics/                     # Saved topic cards & Uncovered Topics banner
│   │   └── lib/                            # API Clients, Auth Context & WebSocket hooks
│
├── campaign/                               # Marketing Campaign & Visual Asset Suite
│   ├── README.md                           # Master campaign documentation
│   ├── flyers/                             # 15 Full-Bleed Marketing Posters (1200x1650 px PNGs & HTML)
│   ├── carousel/                           # 20 Instagram Carousels (130+ slides, 4:5 1080x1350 px)
│   └── assets/screenshots/                 # High-resolution production app screenshots
│
├── mcp/                                    # Model Context Protocol (MCP) Server & Client tools
├── website/                                # Standalone Next.js 16 Marketing Landing Website (port 3100)
├── alembic/                                # Database migration version scripts
├── docker-compose.yml                      # Production multi-container orchestration
├── Dockerfile                              # Python FastAPI / Celery container specification
└── requirements.txt                        # Python backend dependencies
```

---

## 💻 Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| **Backend Framework** | FastAPI 0.115+ (Python 3.10+) | Async REST API, WebSocket streams, rate limiting |
| **Frontend Framework** | Next.js 16 + React 19 + TypeScript | Glassmorphic, responsive, high-performance UI |
| **Styling & Motion** | Tailwind CSS v4 + Framer Motion | Modern dark mode styling, fluid micro-interactions |
| **Relational Database** | PostgreSQL 16 + SQLAlchemy 2.0 + Alembic | Dual async (`asyncpg`) & sync (`psycopg`) database engines |
| **Dual Redis Infrastructure** | Redis 7.0 (2 Isolated Instances) | `redis-broker` (AOF, `noeviction`) + `redis-cache` (`allkeys-lru`) |
| **Task Queue & Scheduler** | Celery 5.4 + Celery Beat + Flower | Distributed generation queues & nightly sync cron jobs |
| **Primary AI Models** | Google Gemini 3.6 Flash & Gemini Image | Content generation, deep channel audits & 4K image renders |
| **LLM Provider Cascade** | NVIDIA NIM · Ollama · Groq · OpenAI | Multi-tier failover & local inference fallback |
| **Vector Database** | Qdrant OSS / Cloud | Document ingestion, RAG, and agent memory |
| **External Integrations** | YouTube Data API v3 · YouTube Analytics API · Meta Graph API · Google Calendar API · Stripe | Live metrics, video sync, token management, calendar scheduling |
| **Security & Cryptography** | Fernet Cryptography + JWT + Double-Submit CSRF | Token encryption, HttpOnly auth cookies, denylist revocation |

---

## 🖥 Dashboard Modules

### 1. Nexus Command Center (`/`)
- **Real-Time Agent Telemetry**: Live progress monitor for running generation pipelines via WebSockets.
- **Approval Queue**: Review, edit, approve, or reject generated scripts, blog posts, and visual assets before publication.
- **Quick Dispatch Actions**: One-click generation for LinkedIn, Blog, YouTube, and Instagram posts.
- **System Health Bar**: Real-time heartbeat of database connections, Redis queues, and LLM providers.

### 2. AI Schedule & Strategy Assistant (`/assistant`)
- **Context-Aware Conversational Assistant**: Chat with an AI assistant that reads your active editorial plans, topic backlog, and synced YouTube/Instagram metrics.
- **Action Proposal Protocol**: Proposes actionable database operations (e.g. creating plan items, updating schedules, generating content) rendered as actionable cards.
- **1-Click Execution**: Confirm or cancel proposed actions with a single click.
- **Zero-Latency Daily Digest (`/digest`)**: Instant overview of scheduled publications and pending tasks for today.

### 3. Topics Backlog & Uncovered Topics Vault (`/topics`)
- **Uncovered Topics Auto-Capture**: When AI research generates a batch of candidate topics, the unused ones are automatically stored in the backlog instead of being lost.
- **Anti-Repetition Engine**: Automatically checks new ideas against previously published content.
- **On-Demand Generation**: Promote any backlog topic to immediate pipeline generation with a single click.

### 4. Cross-Platform Editorial Planner (`/planner`)
- **Weekly & Monthly Calendars**: Flexible scheduling across YouTube, Instagram, LinkedIn, and Tech Blogs.
- **6-Stage Production Tracker**: Visual lifecycle tracking: `pending` → `script_generated` → `presentation_created` → `video_created` → `video_edited` → `video_published`.
- **Google Calendar 2-Way Sync**: Encrypted OAuth integration to create and update calendar reminders automatically.
- **Planner Analytics (`/planner-analysis`)**: Aggregate production velocity and content distribution metrics.

### 5. Gemini Image Studio (`/image-studio`)
- **Prompt-to-Image Synthesis**: Powered by Google Gemini Image models (`gemini-3.1-flash-image`, `gemini-3.1-flash-lite-image`, `gemini-3-pro-image`).
- **Flexible Aspect Ratios & Resolutions**: Support for 4:5 (Instagram portrait), 1:1, 16:9, and sizes from 512px to 4K.
- **Secure Image Streaming**: Authenticated endpoints stream generated assets without exposing direct disk storage.

### 6. YouTube Analytics & Competitor Outlier Engine (`/youtube-analysis` & `/prospects`)
- **Live Sync & Real Metrics**: Live sync of all channel uploads via YouTube Data API v3, plus real watch-time, CTR, and impressions from YouTube Analytics API.
- **Nightly Automated Refresh**: Scheduled Celery Beat sync (12:05 AM IST) keeps video performance data fresh.
- **AI Channel Audit & 1–8 Week Roadmaps**: Gemini 3.6 Flash channel health evaluations, playlist web trend suggestions, and dated multi-week publishing plans.
- **Upload-Timing & Best Schedule Intelligence**: Mathematical analysis of upload timestamps across the channel's top-performing & breakout videos, calculating the exact peak day(s) and time windows (with view velocity lift % and 7-day interactive heatmap).
- **Competitor Outlier Tracking (`/api/youtube-competitors`)**: Tracks competitor uploads, identifies high-CTR breakout outlier videos, and feeds winning formats into the generation engine.

### 7. Instagram Analytics, Meta Graph & Kanban Board (`/instagram-analysis`)
- **Meta OAuth 2.0 Engine**: Automated 60-day Long-Lived Token exchange with background auto-refresh (<15 days remaining).
- **Three-Tier Read Path**: Ultra-fast caching: Redis Cache → Postgres Snapshot → Meta Graph API.
- **Hashtag Cluster Scoring**: Scored hashtag analysis based on actual reach and engagement metrics.
- **Kanban Content Board**: Visual board managing posts through `idea` → `in_production` → `scheduled` → `published` with 1-click **"Add Roadmap to Board"** action.

### 8. Personal Intelligence Engine (`/personal-intelligence`)
- **Custom Directives & Rules**: Define voice, formatting rules, style constraints, and taboo topics that are dynamically injected into every LLM prompt.
- **Dynamic Goal Tracking**: Set subscriber, reach, or view goals and track automated progress calibrated against live analytics data.

---

## 🤖 Multi-Agent Generation Pipelines

| Pipeline | Queue & Concurrency | Agent Workflow | Output Deliverable |
|---|---|---|---|
| **LinkedIn Post** | `linkedin_queue` (concurrency 4) | Hook Finder → Post Writer → Editor → QA Checker → Approver | Complete post copy, viral hooks, line breaks, hashtag cluster |
| **Technical Blog** | `blog_queue` (concurrency 2) | Web Researcher → Section Writer → Editor → QA Assembler → Approver | Production-ready Markdown blog post with verified code blocks |
| **YouTube Script** | `youtube_queue` (concurrency 2) | Topic Researcher → Script Writer → Editor → QA → SEO Specialist | Full video script, Shorts script, high-CTR titles, description, tags |
| **Visual Assets** | `gpu_queue` (concurrency 1) | Prompt Optimization → Gemini Image Synthesis (`gemini-3.1-flash-image`) | High-resolution 2K/4K social graphic (4:5 portrait, 1:1 square) |

---

## 📋 Prerequisites

- **Python**: 3.10 or higher
- **Node.js**: 18.x or higher with `npm`
- **PostgreSQL**: 16.x (or run via Docker Compose)
- **Redis**: 7.x (two instances: Cache + Broker/State, or run via Docker Compose)
- **Google Gemini API Key**: For text analysis (`gemini-3.6-flash`) and image synthesis (`gemini-3.1-flash-image`).
- **Optional Providers**: NVIDIA NIM, Groq, OpenAI, Anthropic, or local [Ollama](https://ollama.ai).

---

## 🚀 Setup & Installation

### Option A — Docker Compose (Recommended)

Start the entire microservices stack (PostgreSQL, dual Redis, API, Celery workers, Flower, Dashboard) with a single command:

```bash
# 1. Clone the repository
git clone https://github.com/kumardigamberjha/SocialPipeline.git
cd SocialPipeline

# 2. Configure environment variables
cp app/.env.example app/.env
# Edit app/.env to add your GEMINI_API_KEY and custom secrets

# 3. Launch all containers
docker compose up -d

# 4. View service logs
docker compose logs -f api dashboard worker
```

- **Dashboard**: `http://localhost:3000`
- **FastAPI API Docs**: `http://localhost:8000/docs`
- **Flower Task Monitor**: `http://localhost:5555`

---

### Option B — Local Manual Setup

#### 1. Backend Setup
```bash
# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Configure environment file
cp app/.env.example app/.env
# Edit app/.env with your database URL, Redis URLs, and API keys

# Apply database migrations
alembic upgrade head
```

#### 2. Frontend Dashboard Setup
```bash
cd dashboard
npm install

# Configure frontend environment file
echo "NEXT_PUBLIC_BACKEND_API=http://127.0.0.1:8000" > .env
```

---

## 🏃 Running the Services

### 1. Run Database Migrations
```bash
alembic upgrade head
```

### 2. Start FastAPI Backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Start Celery Workers & Beat Scheduler
```bash
# Default worker (celery queue)
celery -A app.celery_app worker -Q celery --concurrency=4 --loglevel=info

# Dedicated platform workers
celery -A app.tasks:app worker -Q linkedin_queue --concurrency=4 --loglevel=info
celery -A app.tasks:app worker -Q blog_queue --concurrency=2 --loglevel=info
celery -A app.tasks:app worker -Q youtube_queue --concurrency=2 --loglevel=info
celery -A app.celery_app worker -Q gpu_queue --concurrency=1 --loglevel=info

# Celery Beat (nightly YouTube & Instagram sync schedules)
celery -A app.celery_app beat --loglevel=info
```

### 4. Start Next.js Dashboard
```bash
cd dashboard
npm run dev
# Dashboard accessible at http://localhost:3000
```

### 5. Start Flower Monitoring (Optional)
```bash
celery -A app.celery_app flower --port=5555
# Flower accessible at http://localhost:5555
```

---

## ⚙️ Environment Configuration

Key configuration options in `app/.env`:

```env
# ── System Environment ───────────────────────────────────────
ENVIRONMENT=development                     # development | production
LOG_LEVEL=INFO

# ── Primary Database (PostgreSQL 16) ─────────────────────────
DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20

# ── Redis Architecture (Dual Instance) ───────────────────────
REDIS_CACHE_URL=redis://localhost:6379/0    # Analytics & AI cache (allkeys-lru)
REDIS_STATE_URL=redis://localhost:6380/2    # Auth denylist & WS tickets (noeviction)
CELERY_BROKER_URL=redis://localhost:6380/0  # Celery task queue broker
CELERY_RESULT_BACKEND=redis://localhost:6380/1

# ── Auth & Security ──────────────────────────────────────────
SECRET_KEY=generate-a-secure-64-character-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_TTL_SECONDS=900               # 15 minutes (HttpOnly cookie)
REFRESH_TOKEN_TTL_SECONDS=2592000          # 30 days (HttpOnly cookie)

# ── Token Encryption (Fernet) ────────────────────────────────
TOKEN_ENCRYPTION_KEY=                      # python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ── Primary AI & LLM Providers ───────────────────────────────
DEFAULT_PROVIDER=google                    # google | nvidia | ollama | groq | openai | anthropic
ANALYSIS_MODEL=gemini/gemini-3.6-flash
GEMINI_API_KEY=your_gemini_api_key
GEMINI_BACKUP_API_KEY=                     # Optional secondary failover key

# ── Gemini Image Synthesis ───────────────────────────────────
GEMINI_IMAGE_MODEL=gemini-3.1-flash-image  # gemini-3.1-flash-image | gemini-3-pro-image
GEMINI_IMAGE_ASPECT_RATIO=4:5
GEMINI_IMAGE_SIZE=2K                       # 512 | 1K | 2K | 4K
IMAGE_OUTPUT_DIR=dashboard/public/generated_posts

# ── Meta Instagram Graph API ────────────────────────────────
INSTAGRAM_APP_ID=your_meta_app_id
INSTAGRAM_APP_SECRET=your_meta_app_secret
INSTAGRAM_REDIRECT_URI=http://localhost:8000/api/instagram/oauth/callback

# ── Google Calendar OAuth ────────────────────────────────────
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/google/callback

# ── Email / SMTP (OTP Verification) ──────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
```

---

## 🐳 Docker Compose Services

| Service | Container Port | Host Port | Purpose |
|---|---|---|---|
| `postgres` | `5432` | `127.0.0.1:5433` | PostgreSQL 16 database storage |
| `redis-broker` | `6379` | `127.0.0.1:6380` | Celery broker/results + auth denylist (AOF, `noeviction`) |
| `redis-cache` | `6379` | `127.0.0.1:6379` | Analytics & AI response cache (`allkeys-lru`) |
| `migrate` | — | — | One-shot Alembic migration runner executed before API startup |
| `api` | `8000` | `0.0.0.0:8000` | FastAPI backend application server |
| `worker` | — | — | Default Celery task worker (`celery` queue) |
| `linkedin_worker` | — | — | Dedicated LinkedIn generation worker (`linkedin_queue`) |
| `blog_worker` | — | — | Dedicated technical blog worker (`blog_queue`) |
| `gpu_worker` | — | — | Gemini visual rendering worker (`gpu_queue`) |
| `flower` | `5555` | `127.0.0.1:5555` | Celery task monitoring dashboard |
| `dashboard` | `3000` | `0.0.0.0:3000` | Next.js 16 frontend web dashboard |

---

## 🔌 Model Context Protocol (MCP) Support

The repository includes a built-in **Model Context Protocol (MCP)** server and client implementation in `mcp/`:
- **Server (`mcp/server.py`)**: Exposes live analytics tools (e.g. `get_youtube_channel_stats`) via FastMCP with streamable HTTP transport on port `8001`.
- **Client (`mcp/client.py`)**: Connects to the MCP server to inspect tools and execute remote agent capabilities seamlessly.

To launch the MCP server:
```bash
python mcp/server.py
```

---

## 🎨 Marketing Campaign & Media Suite

The repository includes complete, ready-to-publish marketing assets and automated rendering scripts in `campaign/` and `website/`:

- **15 Full-Bleed Graphic Marketing Flyers** (`campaign/flyers/images/` at 1200x1650 px): Professional high-resolution graphic posters highlighting architecture, AI pipelines, competitor tracking, and case studies.
- **20 Multi-Slide Instagram Carousels** (`campaign/carousel/images/` at 1080x1350 px, 4:5): Over 130+ slide PNGs with complete `caption.txt` files containing hooks, copy, and hashtag clusters.
- **Interactive Browser Studios**:
  - `campaign/flyers/index.html` — Interactive flyer preview gallery.
  - `campaign/carousel/index.html` — Interactive mobile carousel simulator with 1-click caption copy.
- **Automated Video Assembly**:
  - `build_final_synchronized_videos.py` — Synchronized video generation pipeline combining TTS audio, screenshots, and motion text overlays.
  - `build_release_film.py` — High-definition promo video assembler.
- **Marketing Landing Website (`website/`)**: Standalone Next.js 16 marketing website (runs on port 3100) featuring 3D Blender animations and interactive feature breakdowns.

---

## 🔒 Security & Authentication Model

1. **HttpOnly Cookie Tokens**: Tokens are delivered as `nx_at` (15-minute access token) and `nx_rt` (30-day refresh token) HttpOnly cookies, completely eliminating XSS token theft.
2. **Double-Submit CSRF Protection**: Every mutating state request requires matching `nx_csrf` cookie and `X-CSRF-Token` headers.
3. **Redis Revocation Denylist**: When a user logs out or rotates passwords, the token JTI is added to the `redis-broker` denylist with an exact TTL match.
4. **Encrypted Token Vault**: All third-party OAuth credentials (Meta Instagram & Google Calendar) are encrypted using symmetric Fernet cryptography before database persistence.
5. **Boot-Time Auth Guard**: FastAPI inspects every registered route at startup to verify that each route either declares explicit authentication dependencies or is registered in `PUBLIC_ROUTES`.

---

## 📄 License & Contribution

Built for the **MyEmpire** content ecosystem — powering developer content creation for [@codingindiaai](https://instagram.com/codingindiaai).

1. Fork the repository and create a feature branch (`git checkout -b feature/amazing-feature`).
2. Commit your changes following conventional commits (`git commit -m 'feat: add amazing feature'`).
3. Push to your origin branch (`git push origin feature/amazing-feature`).
4. Open a Pull Request for review.

---

<div align="center">
  <sub>Built with ❤️ by the Wings of AI / Content Manager Engineering Team.</sub>
</div>
