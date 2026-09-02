# Earnings Call Intelligence

An AI-powered system for analyzing earnings call transcript PDFs. It extracts structured Q&A units, identifies speakers and their roles, detects strategic statements, and provides an interactive web interface with a streaming chatbot — powered by OpenRouter-hosted LLMs.

---

## What It Does

Upload a PDF earnings call transcript and the system will:

- **Extract and clean** the full text from the PDF
- **Detect section boundaries** (opening remarks, Q&A session, closing)
- **Build a speaker registry** — canonical names, roles (management / analyst / moderator), titles, companies
- **Extract Q&A units** — each question paired with its answer, follow-up chains linked to parent questions
- **Extract strategic statements** from opening and closing remarks
- **Provide a web UI** to explore all results, browse LLM decision traces, and ask questions in a streaming chat

---

## Architecture

```
PDF
 │
 ▼
Pipeline V2 (Python)
 ├── Stage 0: PDF Extraction + Text Cleaning
 ├── Stage 1: Metadata Extraction         (company, ticker, quarter, year)
 ├── Stage 2: Boundary Detection          (section types and offsets)
 ├── Stage 3: Speaker Registry            (roles, aliases, deduplication)
 ├── Stage 4: Q&A Block Extraction        (regex blocks → LLM structures)
 └── Stage 5: Strategic Extraction        (opening/closing statements)
 │
 ▼
JSON files  ──▶  FastAPI Backend  ──▶  React Frontend
                      │
                      └──▶  Chatbot (SSE streaming, full-transcript context)
```

**Philosophy**: *Regex proposes (high recall) → LLM structures (semantic understanding) → Code enforces invariants (correctness)*

---

## Tech Stack

### Pipeline
| Library | Purpose |
|---------|---------|
| `pdfplumber` | PDF text extraction |
| `langchain` + `langchain-openai` | LLM orchestration |
| `OpenRouter` | Hosted LLM inference (`openai/gpt-oss-20b`, fallback `google/gemma-3-27b-it`) |
| `pydantic` + `pydantic-settings` | Data models and `.env` config |
| `rapidfuzz` | Speaker name deduplication (fuzzy matching) |
| `structlog` | Structured logging |

### Web Application
| Component | Library |
|-----------|---------|
| Backend | FastAPI, uvicorn, aiofiles |
| Frontend | React 18, TypeScript, Vite |
| Styling | Tailwind CSS, shadcn/ui, Framer Motion |
| Charts | Recharts |

---

## Requirements

- **Python 3.10+**
- **Node.js 18+** (only for rebuilding the frontend)
- An **[OpenRouter](https://openrouter.ai)** API key (used by both the pipeline and the chatbot; no local model install needed)

---

## Quick Start

### 1. Clone and install Python dependencies

```bash
git clone <repo-url>
cd earnings-call-intelligence

python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -e .
```

### 2. Configure environment

Copy `.env.example` to `.env` and add your OpenRouter API key:

```env
OPENROUTER_API_KEY=sk-or-...
LLM_MODEL_NAME=openai/gpt-oss-20b          # default, override to switch models
LLM_FALLBACK_MODEL_NAME=google/gemma-3-27b-it
LLM_TEMPERATURE=0.0
LLM_REQUEST_TIMEOUT=120
```

### 3. Start the web application

```bash
cd backend
pip install -r requirements.txt
# create backend/.env with JWT_SECRET_KEY, MySQL creds (auth), and OPENROUTER_API_KEY (chatbot)
uvicorn main:app --reload --port 8100
```

Open **http://localhost:8100** — the compiled frontend is served directly by FastAPI.

---

## Web UI

Upload a PDF via the header button and watch the pipeline stages complete in real time.

| Tab | What you see |
|-----|-------------|
| **Overview** | Stats, live pipeline stage stepper, charts, errors/warnings |
| **Speakers** | Speaker registry with roles, titles, companies, LLM reasoning |
| **Q&A Explorer** | Question/answer pairs, follow-up chains, page references |
| **Analyst Summary** | Questions grouped by analyst with stats |
| **Traces** | Per-stage LLM decisions and evidence spans |
| **Raw Text** | Extracted text per page |
| **Raw JSON** | Full pipeline output |
| **Chat** | Streaming chatbot — ask anything about the transcript |

---

## CLI Usage

The pipeline can also be run from the command line without the web UI:

```bash
# Run V2 pipeline (recommended)
python scripts/run_pipeline_v2.py data/input/transcript.pdf

# Skip enrichment for faster processing
python scripts/run_pipeline_v2.py data/input/transcript.pdf --skip-enrichment

# Original CLI entry point
eci analyze data/input/transcript.pdf -o data/output/report.json
```

---

## Project Structure

```
earnings-call-intelligence/
├── pyproject.toml                  # Project config and dependencies
├── .env                            # Environment configuration
├── CLAUDE.md                       # Developer reference (architecture, decisions, changelog)
├── WEB_APP_README.md               # Web application detailed documentation
│
├── src/                            # Pipeline source code
│   ├── cli.py                      # CLI entry point (eci command)
│   ├── llm/
│   │   └── client.py               # OpenRouter (ChatOpenAI) client, model settings
│   ├── extraction/
│   │   └── pdf_extractor.py        # pdfplumber PDF extraction
│   └── pipeline_v2/                # Current pipeline (V2)
│       ├── models.py               # PipelineV2State + all stage models
│       ├── orchestrator.py         # run_pipeline_v2() — coordinates all stages
│       ├── llm_helpers.py          # Prompt builders, LLM invoke with retry
│       └── stages/
│           ├── boundary.py         # Section boundary detection
│           ├── speakers.py         # Speaker registry builder
│           ├── qa_block_processor.py  # Block-by-block Q&A extraction
│           ├── strategic.py        # Strategic statement extraction
│           ├── text_cleaner.py     # Regex noise removal
│           └── enrichment.py       # Optional topic/intent enrichment
│
├── backend/                        # FastAPI web backend
│   ├── main.py                     # App entry point, static file serving
│   ├── requirements.txt
│   ├── api/
│   │   ├── routes/                 # upload, analyze, results, traces, chat
│   │   └── schemas/                # Request/response Pydantic models
│   ├── services/
│   │   ├── storage.py              # JSON file read/write
│   │   ├── pipeline_runner.py      # Async pipeline execution bridge
│   │   ├── chat_agent.py           # Chatbot: prompt, SSE stream, citations
│   │   └── chat_data_loader.py     # Cached data loading for chatbot
│   ├── static/                     # Compiled frontend (served at /)
│   └── data/
│       ├── uploads/                # Uploaded PDFs
│       └── runs/                   # Analysis results (JSON files per run)
│
└── frontend/                       # React frontend source
    ├── src/
    │   ├── App.tsx
    │   ├── api/client.ts
    │   ├── types/api.ts
    │   └── components/
    │       ├── Header.tsx
    │       ├── RunsTable.tsx
    │       ├── RunDetail.tsx
    │       ├── chat/
    │       └── tabs/
    └── ...
```

---

## LLM Models

| Component | Model | Fallback | Notes |
|-----------|-------|----------|-------|
| Pipeline (all stages) | `openai/gpt-oss-20b` | `google/gemma-3-27b-it` | via OpenRouter |
| Chatbot | `openai/gpt-oss-20b` (override with `CHAT_LLM_MODEL`) | — (no fallback) | via OpenRouter, own `OPENROUTER_API_KEY` in `backend/.env` |

The pipeline retries failed LLM calls up to 3 times with escalating temperature (`0.0 → 0.2 → 0.5`), then falls back to `google/gemma-3-27b-it`.

To switch the pipeline model, set `LLM_MODEL_NAME=` in `.env` to any [OpenRouter model slug](https://openrouter.ai/models).

---

## Development

```bash
# Install with dev extras (pytest, ruff, mypy)
pip install -e ".[dev]"

# Lint
ruff check src/

# Type check
mypy src/

# Run tests
pytest

# Rebuild frontend after UI changes
cd frontend
npm run build -- --outDir ../backend/static --emptyOutDir
```

---

## Data Management

All run data is stored as JSON files under `backend/data/runs/{run_id}/`. No database required.

```bash
# Delete a specific run (API)
curl -X DELETE http://localhost:8100/runs/{run_id}

# Delete all runs
rm -rf backend/data/runs/*

# Delete uploaded PDFs
rm -rf backend/data/uploads/*
```

---

## Deployment

The backend deploys to **Render** (`render.yaml`) and the frontend to **Vercel** (`frontend/vercel.json`, root directory set to `frontend/`).

Required env vars:
- Render: `JWT_SECRET_KEY` (app won't boot without it), `CORS_ORIGINS` (comma-separated, set to your Vercel domain), plus `OPENROUTER_API_KEY` and the MySQL vars from Quick Start above.
- Vercel: `VITE_API_URL` set to `https://<your-render-service>.onrender.com/api`.

**Note**: uploads and run data are stored on local disk (see Data Management below), which Render's default web service wipes on every redeploy/restart — there's no persistent disk or object storage configured yet.

---

## Known Limitations

- **`gpt-oss-20b` EOS loops** — the model occasionally returns empty responses on certain prompt content, even via OpenRouter. The pipeline handles this with retries and a `google/gemma-3-27b-it` fallback, but a ~5% failure rate on individual blocks is normal. The chatbot has no model fallback — an empty response there is retried once with a simplified prompt.
- **Long transcripts** — very large PDFs (100+ pages) may approach the context window limit for some stages.
- **No offline mode** — the pipeline and chatbot require network access to OpenRouter; there is no local-model fallback.
- **Windows console encoding** — Unicode characters in log output may cause issues on Windows. Use `PYTHONIOENCODING=utf-8` if needed.
- **Synchronous pipeline** — the pipeline runs all stages sequentially in a thread pool. There is no parallelism between stages.
