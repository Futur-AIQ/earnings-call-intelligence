# Earnings Call Intelligence

An AI-powered system for analyzing earnings call transcript PDFs. It extracts structured Q&A units, identifies speakers and their roles, detects strategic statements, and provides an interactive web interface with a streaming chatbot — all running locally via Ollama.

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
| `langchain` + `langchain-ollama` | LLM orchestration |
| `Ollama` | Local LLM inference (`gpt-oss:20b`, fallback `gemma3:latest`) |
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
- **[Ollama](https://ollama.com)** running locally with at least one model pulled:

```bash
ollama pull gpt-oss:20b      # primary model
ollama pull gemma3:latest    # fallback model
```

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

Copy `.env` and set your model:

```env
LLM_OLLAMA_BASE_URL=http://localhost:11434
# LLM_MODEL_NAME=gpt-oss:20b     ← default (hardcoded), uncomment to override
LLM_FALLBACK_MODEL_NAME=gemma3:latest
LLM_TEMPERATURE=0.0
LLM_REQUEST_TIMEOUT=300
LLM_NUM_CTX=16384
```

### 3. Start the web application

```bash
cd backend
pip install -r requirements.txt
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
│   │   └── client.py               # OllamaLLM client, model settings
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

| Component | Model | Fallback | Context Window |
|-----------|-------|----------|----------------|
| Pipeline (all stages) | `gpt-oss:20b` | `gemma3:latest` | 16 384 tokens |
| Chatbot | `gpt-oss:20b` | — | 65 536 tokens |

The pipeline retries failed LLM calls up to 3 times with escalating temperature (`0.0 → 0.2 → 0.5`), then falls back to `gemma3:latest`.

To switch the pipeline model, set `LLM_MODEL_NAME=gemma3:latest` in `.env`.

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

## Known Limitations

- **`gpt-oss:20b` EOS loops** — the model occasionally returns empty responses on certain prompt content. The pipeline handles this with retries and a `gemma3:latest` fallback, but a ~5% failure rate on individual blocks is normal.
- **Long transcripts** — very large PDFs (100+ pages) may approach the context window limit for some stages. The chatbot uses a 65K context window to mitigate this.
- **Windows console encoding** — Unicode characters in log output may cause issues on Windows. Use `PYTHONIOENCODING=utf-8` if needed.
- **Synchronous pipeline** — the pipeline runs all stages sequentially in a thread pool. There is no parallelism between stages.
