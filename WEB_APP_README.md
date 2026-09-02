# Earnings Call Intelligence — Web Application

A production-grade web application for analyzing earnings call transcripts with AI-powered extraction, full decision traceability, and a streaming chatbot.

## Architecture

```
┌──────────────────────┐     ┌──────────────────────┐     ┌──────────────────────┐
│                      │     │                      │     │                      │
│   React Frontend     │────▶│   FastAPI Backend    │────▶│   Pipeline V2        │
│   (TypeScript/Vite)  │     │   port 8100          │     │   (LLM Analysis)     │
│   served from        │     │                      │     │   gpt-oss:20b        │
│   backend/static/    │     │                      │     │                      │
└──────────────────────┘     └──────────────────────┘     └──────────────────────┘
                                        │
                                        ▼
                              ┌──────────────────────┐
                              │   Chatbot (SSE)      │
                              │   full-text stuffing │
                              │   gpt-oss:20b        │
                              └──────────────────────┘
```

## Tech Stack

### Backend
- **FastAPI** — Async Python web framework
- **Pydantic v2** — Data validation and serialization
- **uvicorn** — ASGI server
- **JSON file storage** — No database required

### Frontend
- **React 18** — UI framework
- **TypeScript** — Type safety
- **Vite** — Build tool (output built into `backend/static/`)
- **Tailwind CSS** — Styling (DM Sans body font, DM Serif Display for h1 display titles)
- **shadcn/ui** — Component library (Radix UI primitives)
- **Framer Motion** — Animations
- **Recharts** — Charts (speaker role donut, Q&A composition bar in Overview tab)

---

## Quick Start

### Option A — Backend only (frontend pre-built)

The frontend is already compiled into `backend/static/`. Just start the backend:

```bash
cd backend
python -m venv venv
venv\Scripts\activate       # Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8100
```

Open `http://localhost:8100` — FastAPI serves the compiled React app from `backend/static/`.

### Option B — Backend + Frontend dev server (hot reload)

```bash
# Terminal 1: Backend
cd backend
venv\Scripts\activate
uvicorn main:app --reload --port 8100

# Terminal 2: Frontend dev server
cd frontend
npm install
npm run dev                 # http://localhost:5173 (proxies API to :8100)
```

### Rebuild frontend after UI changes

```bash
cd frontend
npm run build -- --outDir ../backend/static --emptyOutDir
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload a PDF file |
| POST | `/analyze` | Start analysis on an uploaded file |
| GET | `/runs` | List all analysis runs |
| GET | `/runs/{run_id}/summary` | Run summary stats + stage statuses |
| GET | `/runs/{run_id}/speakers` | Speaker registry |
| GET | `/runs/{run_id}/qa` | Q&A units |
| GET | `/runs/{run_id}/traces` | LLM decision traces |
| GET | `/runs/{run_id}/raw` | Raw extracted text |
| GET | `/runs/{run_id}/json` | Full pipeline JSON output |
| DELETE | `/runs/{run_id}` | Delete a run and its files |
| POST | `/runs/{run_id}/chat` | Streaming chatbot (SSE) |

---

## UI Features

### Runs Table (home screen)
- Lists all runs with filename, status badge, start time, speaker count, Q&A count
- View and Delete buttons per row
- Auto-refreshes every 3s while any run is in `running` state

### Overview Tab
- **Stats cards**: Pages, Speakers, Q&A Units, Follow-ups
- **Pipeline stage stepper**: 6 stages with live status (pending → running → completed)
  - Stages: PDF Extraction, Metadata, Boundary Detection, Speaker Registry, Q&A Extraction, Strategic Statements
  - Updates in real time during a pipeline run via polling
- **Insights charts** (completed runs only): Speaker role donut, Q&A composition bar
- **Run Status card**: status badge, timestamps, duration, text length
- **Issues panel**: errors and warnings from all stages

### Speakers Tab
- Table: canonical name, role badge, title, company, turn count
- Expandable row: aliases, LLM verification reasoning

### Q&A Explorer Tab
- Question/answer pair cards with questioner name and company
- Follow-up chain visualization (linked back to parent question)
- Page references
- Expandable source turns with full text

### Analyst Summary Tab
- **Stats bar**: total analysts, total questions, most active analyst, avg questions per analyst
- **Analyst list sidebar**: sorted by question count descending; click to select
- **Question detail**: numbered list of all questions from the selected analyst

### Traces Tab
- Per-stage LLM decision log
- Input context, output, evidence spans
- Boundary detection candidates and confirmations
- Speaker role decisions with evidence
- Q&A block classifications

### Raw Text Tab
- Per-page extracted text with character counts

### Raw JSON Tab
- Full `pipeline_output.json` content
- Copy to clipboard button

### Chat Drawer
- Slide-in chat panel per run (bottom-right button)
- **Streaming responses** via SSE — text appears token by token
- Conversation history (last 5 turns)
- Citation extraction: `[qa_XXX]`, `[page_N]`, `[speaker_XXX]` references
- Pre-checks for greetings / thanks / history questions (no LLM call)
- Retry on empty response with simplified prompt

---

## Chatbot Architecture

```
User question
    │
    ├── Regex pre-checks (no LLM, instant)
    │   ├── Greeting / thanks       → canned response
    │   └── "What did I ask?"       → from history[]
    │
    ├── load_full_transcript(run_id) ← @lru_cache — reads pipeline_output.json
    │
    ├── _build_prompt()
    │   ├── System: company + rules (cite, no fabrication)
    │   ├── Body:   FULL transcript text
    │   ├── History: last 5 turns (assistant truncated to 1000 chars)
    │   └── "User: {question}\nAssistant:"
    │
    ├── OllamaLLM(gpt-oss:20b, streaming=True, num_ctx=65536)
    │   └── SSE stream → frontend
    │       ├── event: metadata   (retrieval_source)
    │       ├── event: token      (text chunk × N)
    │       └── event: done       (citations, timing)
    │
    └── Retry on empty: simplified prompt, non-streaming
```

**Files**: `backend/services/chat_agent.py`, `backend/services/chat_data_loader.py`

---

## LLM Models

| Component | Primary | Fallback | Context |
|-----------|---------|----------|---------|
| Pipeline (all stages) | `gpt-oss:20b` | `gemma3:latest` | 16 384 tokens |
| Chatbot | `gpt-oss:20b` | — (one retry only) | 65 536 tokens |

Pipeline retry strategy: 3× primary with temperature escalation (0.0 → 0.2 → 0.5), then one attempt with `gemma3:latest`.

To switch the pipeline primary model, set in `.env`:
```env
LLM_MODEL_NAME=gemma3:latest
```

---

## Data Storage

All data is JSON files — no database.

```
backend/data/
├── uploads/
│   └── {file_id}_{filename}.pdf
└── runs/
    └── {run_id}/
        ├── metadata.json               # Status, timestamps, counts, stage statuses
        ├── pipeline_output.json        # Full PipelineV2State (used by chatbot)
        ├── stage_extraction_result.json
        ├── stage_metadata_result.json
        ├── stage_boundary_result.json
        ├── stage_speakers_result.json
        ├── stage_speakers_trace.json
        ├── stage_qa_result.json
        ├── stage_qa_trace.json
        └── stage_strategic_result.json
```

### Delete data

```bash
# Single run (API)
curl -X DELETE http://localhost:8100/runs/{run_id}

# All runs
rm -rf backend/data/runs/*

# All uploads
rm -rf backend/data/uploads/*
```

---

## Project Structure

```
backend/
├── main.py                     # FastAPI app, mounts static/, includes routers
├── requirements.txt
├── api/
│   ├── routes/
│   │   ├── upload.py           # POST /upload
│   │   ├── analyze.py          # POST /analyze
│   │   ├── results.py          # GET /runs, /runs/{id}/*
│   │   ├── traces.py           # GET /runs/{id}/traces
│   │   └── chat.py             # POST /runs/{id}/chat  (SSE)
│   └── schemas/
│       ├── requests.py
│       └── responses.py
├── services/
│   ├── storage.py              # JSON read/write helpers
│   ├── pipeline_runner.py      # Bridges FastAPI ↔ Pipeline V2
│   ├── chat_agent.py           # Chatbot: prompt build, SSE stream, citations
│   └── chat_data_loader.py     # lru_cache data loading for chatbot
├── static/                     # Compiled frontend (served at /)
│   ├── index.html
│   └── assets/
└── data/
    ├── uploads/
    └── runs/

frontend/
├── index.html                  # Loads Google Fonts (DM Sans, DM Serif Display)
├── vite.config.ts              # Dev proxy → :8100
├── tailwind.config.js
└── src/
    ├── main.tsx
    ├── App.tsx                 # Router: table view ↔ run detail view
    ├── index.css               # CSS variables, font rules, scrollbar
    ├── api/client.ts           # Typed fetch wrappers
    ├── types/api.ts            # TypeScript interfaces
    └── components/
        ├── Header.tsx          # Logo + upload button
        ├── RunsTable.tsx       # Home screen table with auto-refresh
        ├── RunDetail.tsx       # Tabbed detail view
        ├── Sidebar.tsx
        ├── chat/
        │   ├── ChatDrawer.tsx  # Slide-in chat panel, SSE consumer
        │   └── ChatMessage.tsx # Message bubble renderer
        ├── tabs/
        │   ├── OverviewTab.tsx
        │   ├── SpeakersTab.tsx
        │   ├── QAExplorerTab.tsx
        │   ├── AnalystSummaryTab.tsx
        │   ├── TracesTab.tsx
        │   ├── RawTextTab.tsx
        │   └── RawJsonTab.tsx
        └── ui/                 # shadcn/ui primitives
```

---

## Design Decisions

**Why JSON storage?**
No database setup. All artifacts are human-readable, easy to inspect with any text editor, and trivial to back up or share.

**Why full-text stuffing for the chatbot?**
Simpler than the previous 2-phase tool-calling architecture (tool selection JSON → grounded synthesis). One LLM call with the transcript in the system prompt is more reliable with `gpt-oss:20b`, which has inconsistent tool-call formatting. Streaming makes latency imperceptible.

**Why separate pipeline traces?**
Every LLM decision is captured with input context, output, and reasoning. This makes prompt iteration fast and the system fully auditable.

**Why pre-built frontend in `backend/static/`?**
Eliminates the need to run two processes in production. FastAPI serves the compiled assets directly. The dev server with hot reload is still available for UI development.

**Why `DM Sans` for headings (h2/h3)?**
`DM Serif Display` is only loaded at weight 400. Browsers synthesize bold by thickening strokes, which looks artificially heavy at card-title sizes. `DM Sans` has proper semibold (600) and looks clean at small scale. `DM Serif Display` is reserved for large h1 display use only.
