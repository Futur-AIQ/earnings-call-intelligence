# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A Python pipeline that analyzes earnings call transcript PDFs and produces structured JSON reports with Q&A units, strategic statements, topics, and evidence references. Includes a FastAPI + React web application for interactive analysis and debugging.

## Tech Stack

### Pipeline
- **Python 3.10+** (pyproject.toml requires `>=3.10`; README says 3.12+ — 3.10 is the enforced minimum)
- **LangChain / LangGraph** - LLM orchestration
- **Ollama** - Local LLM inference
  - Primary model: `gpt-oss:20b` (hardcoded default in `src/llm/client.py`)
  - Fallback model: `gemma3:latest` (after 3 failed primary attempts)
  - Override via `LLM_MODEL_NAME=` in `.env`
- **pdfplumber** - PDF text extraction
- **Pydantic** - Data models and validation

### Web Application
- **Backend**: FastAPI, Pydantic v2, aiofiles, uvicorn, SQLAlchemy + PyMySQL (auth only), PyJWT, bcrypt
- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Framer Motion

## Commands

### Pipeline (root directory)

```bash
# Setup
python -m venv .venv && source .venv/bin/activate   # .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Run the pipeline
python scripts/run_pipeline_v2.py data/input/transcript.pdf          # V2 pipeline (recommended)
python scripts/run_pipeline_v2.py data/input/transcript.pdf --skip-enrichment
python -m src.cli analyze <pdf_path> -o <output.json> -v             # original CLI/pipeline

# Tests (pytest, asyncio_mode=auto, testpaths=tests)
pytest
pytest tests/unit/test_models.py
pytest tests/unit/test_models.py::TestPageContent -v
pytest -k "qa_extraction"

# Lint / type-check
ruff check .
mypy src
```

### Backend (`backend/`)

```bash
cd backend
python -m venv venv && source venv/bin/activate      # venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn main:app --reload --port 8100                # or: python main.py
```

- API docs: http://localhost:8100/docs
- Requires a `backend/.env` with `JWT_SECRET_KEY` (raises `RuntimeError` at import time if unset) and MySQL credentials (`MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`) for the auth subsystem. Neither is in the root `.env.example` — auth is a separate concern from pipeline config.
- Manage users: `python scripts/manage_users.py` (interactive) or `python scripts/manage_users.py create <username> <password> [--role admin|user]` (run from `backend/`)

### Frontend (`frontend/`)

```bash
cd frontend
npm install
npm run dev          # dev server at http://localhost:5173

# Rebuild into backend/static/ (backend serves this SPA in production/non-dev mode)
npm run build -- --outDir ../backend/static --emptyOutDir
```

## Architecture

### Two parallel extraction pipelines

`src/pipeline/` is the original LangGraph pipeline (still present, `src/pipeline/graph.py` + `nodes/`). `src/pipeline_v2/` is the current, actively developed pipeline and is what both the CLI (`run_pipeline_v2.py`) and the web backend (`pipeline_runner.py`) use. When making changes, confirm which pipeline a request concerns — don't assume `src/pipeline/` is dead code without checking, but new work should target `pipeline_v2`.

### Pipeline V2 stage flow

Philosophy: **"Rules propose → LLM restructures → Code enforces invariants"**

```
PDF Input
    │
    ▼
Stage 0: PDF Extraction (pdfplumber)  →  Stage 0B: Text Cleaning (regex: headers/markers)
    │
    ▼
Stage 1: Metadata Extraction (first 1-2 pages, LLM)
    │
    ▼
Stage 2: Boundary Detection (deterministic regex + LLM confirmation)
    │
    ▼
Stage 3: Speaker Registry (rule-based roles + LLM verification, rapidfuzz dedup)
    │
    ├──────────────────────────────┐
    ▼                               ▼
Stage 4: Q&A Extraction        Stage 5: Strategic Extraction
(regex detects blocks via      (opening/closing remarks only)
 qa_block_processor.py, LLM
 structures each block)
    │                               │
    └───────────┬───────────────────┘
                ▼
Enrichment (optional, skip_enrichment=True by default)
NOT tracked in UI stepper — topics, intent, posture
```

**UI stepper tracks exactly 6 stages**: extraction, metadata, boundary, speakers, qa, strategic. Each fires `stage_callback(name, "running")` then `stage_callback(name, "completed")` in `src/pipeline_v2/orchestrator.py`. `backend/services/pipeline_runner.py`'s callback writes status to `metadata.json` live via `asyncio.run_coroutine_threadsafe` (the pipeline runs in a worker thread, not the event loop).

**Block-based Q&A extraction rules** (`src/pipeline_v2/stages/qa_block_processor.py`, `boundary.py`):
- Regex output is HIGH-RECALL and MUST be respected — regex detects Q&A blocks (investor introductions), never the LLM
- LLM structures each block into Q&A pairs; it may EXTEND or MERGE content but never remove it, and MUST return a result for every block (`is_valid: false` rather than a silent drop)
- Questions/answers must be complete (no truncation); multi-speaker answers are valid; follow-ups link backward to the parent question

### Key models (`src/pipeline_v2/models.py`)

| Model | Purpose |
|-------|---------|
| `PipelineV2State` | Complete pipeline state — all stage outputs and traces |
| `ExtractedMetadata` | Company, ticker, quarter, year, date |
| `BoundaryDetectionResult` | Sections with types and offsets |
| `SpeakerRegistry` | Canonical names, aliases, roles |
| `QAExtractionResult` | Q&A units with follow-up chains |
| `StrategicExtractionResult` | Strategic statements |

Note the naming mismatch that `pipeline_runner.py` has to bridge: `PipelineV2State` uses `raw_text`, `qa_extraction_result`, `strategic_extraction_result` — not `raw_document` / `qa_result` / `strategic_statements`.

Each stage also stores inspectable decision traces for debugging: `boundary_trace`, `speaker_registry_trace`, `qa_extraction_trace` — surfaced in the frontend's Traces tab.

### Backend structure (`backend/`)

```
backend/
├── main.py                  # FastAPI app; mounts routers under both /api/* and unprefixed
│                             #   (unprefixed exists for the Vite dev proxy, which strips /api)
│                             # Serves backend/static/ as an SPA catch-all when no API/asset route matches
├── database.py               # SQLAlchemy engine/session (MySQL via PyMySQL) — auth only
├── models/user.py             # User ORM model (username, password_hash, role, is_active)
├── api/
│   ├── auth.py                # bcrypt hashing + JWT encode/decode (JWT_SECRET_KEY required)
│   ├── deps.py                 # get_current_user (optional) / require_auth (401 if missing) FastAPI deps
│   └── routes/
│       ├── auth.py             # POST /auth/login
│       ├── upload.py           # POST /upload
│       ├── analyze.py          # POST /analyze
│       ├── results.py          # GET /runs, /runs/{id}/*
│       ├── traces.py           # GET /runs/{id}/traces
│       └── chat.py             # POST /runs/{id}/chat, /runs/{id}/chat/stream (SSE)
├── services/
│   ├── storage.py              # JSON file storage for run data (the actual system of record)
│   ├── pipeline_runner.py      # Bridges pipeline_v2 orchestrator into async FastAPI + live stage status
│   ├── chat_agent.py           # Chat LLM calls (full-transcript prompt, SSE streaming)
│   └── chat_data_loader.py     # Loads/caches pipeline_output.json per run (@lru_cache)
└── data/
    ├── uploads/                 # Uploaded PDFs
    └── runs/{run_id}/           # metadata.json, stage_*_result.json, stage_*_trace.json, pipeline_output.json
```

**Auth is a bolt-on, not the primary data layer**: run/analysis data is entirely JSON-on-disk (see `storage.py`); MySQL only backs the `users` table for login. If MySQL is unreachable, `init_db()` fails at startup with a caught warning — the rest of the API still works, just without auth. `require_auth` vs `get_current_user` in `deps.py` determine whether a route is auth-gated or auth-optional; check which routes currently use which before assuming the whole API is locked down.

### Chatbot (`backend/services/chat_agent.py` + `chat_data_loader.py`)

**Model**: `gpt-oss:20b`, `num_ctx=65536`, `temperature=0.1`, `num_predict=4096` — hardcoded here, independent of the pipeline's `.env` LLM settings.
**Transport**: SSE via `POST /runs/{run_id}/chat/stream`.

```
User question
    │
    ├── Regex pre-checks (no LLM): greeting/thanks → canned response; "what did I ask?" → from history[]
    ├── load_full_transcript(run_id)  ← @lru_cache, reads pipeline_output.json
    ├── _build_prompt(): system (company/quarter + citation/no-fabrication rules) + full transcript
    │                     + last 5 history turns (assistant truncated to 1000 chars) + question
    ├── OllamaLLM.stream() → SSE: event:metadata (retrieval_source) → event:token × N → event:done (citations, timing)
    └── Retry once on empty response (simplified prompt, non-streaming) — no model fallback here (see Known Issues)
```

Citations are extracted via regex over `[qa_XXX]`, `[page_N]`, `[speaker_XXX]` patterns in the LLM's answer. `load_run_data()` and `load_full_transcript()` are both `@lru_cache(maxsize=10)` — stale after re-running the same `run_id` (see Known Issues).

## Configuration

### Root `.env` (pipeline)

```env
# LLM_MODEL_NAME=gemma3:latest      ← uncomment to switch primary model
# LLM_MODEL_NAME=gpt-oss:20b        ← current default (hardcoded in src/llm/client.py)
LLM_FALLBACK_MODEL_NAME=gemma3:latest
LLM_TEMPERATURE=0.0
LLM_REQUEST_TIMEOUT=300
LLM_NUM_CTX=16384                   ← pipeline context window
CHUNK_TARGET_TOKENS=2000
CHUNK_OVERLAP_TOKENS=200
```

### `backend/.env` (web app — not templated in `.env.example`, must be created manually)

- `JWT_SECRET_KEY` (required — `api/auth.py` raises at import time if unset), `JWT_ALGORITHM` (default `HS256`), `JWT_EXPIRY_HOURS` (default 24)
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE` (default `call_transcript`)

## Data Storage

All run/analysis data is JSON files, no database (auth's MySQL `users` table is the one exception — see above):

- Uploads: `backend/data/uploads/{file_id}_{filename}.pdf`
- Runs: `backend/data/runs/{run_id}/` — `metadata.json` (status/timestamps/counts), `stage_*_result.json`, `stage_*_trace.json`, `pipeline_output.json` (full state)

```bash
rm -rf backend/data/runs/{run_id}     # delete one run
rm -rf backend/data/runs/*            # delete all runs
rm -rf backend/data/uploads/*         # delete uploads
curl -X DELETE http://localhost:8100/runs/{run_id}
```

## Known Issues

1. **Windows console encoding** — avoid Unicode chars in console output; use `.encode('ascii', errors='replace')`.
2. **gpt-oss:20b EOS loops** — ~30% empty-response rate on certain prompt content. Pipeline retries 3× with escalating temperature (0.0→0.2→0.5) then falls back to `gemma3:latest`. Non-ASCII characters and certain section headings trigger the loop.
3. **Chatbot has no fallback model** — if `gpt-oss:20b` returns empty in the chatbot, only one simplified-prompt retry is attempted (no model switch, unlike the pipeline).
4. **`lru_cache` not invalidated on re-run** — re-analyzing the same `run_id` leaves the chatbot serving stale transcript data from `chat_data_loader.py`'s caches. Call `invalidate_cache()` or restart the backend.
