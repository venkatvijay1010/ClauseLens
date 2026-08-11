# ClauseLens

**Evidence-backed document version comparison for reviewers.**

ClauseLens compares two versions of the same text-based document, detects changes deterministically, and produces a reviewer-friendly report with exact before/after evidence. An optional structured LLM assessment explains the likely significance of each already-detected change; it never decides whether a change exists.

> ClauseLens is review assistance, not legal, compliance, or policy-approval advice.

## Why this project

Teams reviewing vendor terms, privacy notices, employee handbooks, or internal policies need more than a raw text diff. They need to know which changes involve deadlines, payment, privacy, obligations, termination, or eligibility—and they need to see the supporting text immediately.

This project intentionally differs from a RAG chatbot: its core input is **two document versions**, and its core output is a **ranked change report**, not an answer to a user question.

## Core capabilities

- FastAPI and Pydantic API design
- PostgreSQL persistence and Alembic migrations
- Heading-aware document parsing and one-to-one section alignment
- Safe extraction for plain text, text-based PDF, DOCX, and XLSX workbooks
- Deterministic diffing before LLM use for cost and hallucination control
- Structured assessment with a no-key local fallback
- Evidence/citation validation against stored source text
- A browser review workspace with drag-and-drop uploads, filters, expandable evidence, review actions, and database-backed history
- Docker, pytest, Ruff, GitHub Actions, and a reproducible benchmark

## Architecture

```text
Baseline version + revised version
             |
             v
Text extraction / normalization / heading-aware sections
             |
             v
Exact heading match -> conservative fuzzy heading match -> deterministic diff
             |
             v
Structured assessment of changed sections only
             |
             v
Pydantic + source-excerpt validation
             |
             v
PostgreSQL report -> REST API / browser review screen
```

## Quick start

### Option A — Docker (recommended local demo)

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open:

- Demo UI: `http://localhost:8001`
- Interactive API docs: `http://localhost:8001/docs`
- Health endpoint: `http://localhost:8001/health`

The default `.env` uses `LLM_PROVIDER=heuristic`, so the demo works with no API key, model download, or paid model calls.

### Option B — local Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --env-file .env
```

For local SQLite-only exploration, omit `DATABASE_URL`; Docker is the intended PostgreSQL path.

## Demo workflow

1. Open the browser demo and upload a baseline and revised version of the same document.
2. Use UTF-8 text/Markdown, text-based PDF, DOCX, or XLSX files. The default upload limit is 5 MiB per file and is configurable.
3. Click **Run comparison**, then inspect the risk-ranked changes and their exact before/after evidence.
4. Filter by severity or category, expand a change for full detail, and mark it reviewed or dismissed.
5. Open **History** to reload earlier comparisons stored in the configured database.

Sample source versions live in [`data/sample`](data/sample).

## Browser review workspace

The built-in interface is designed for focused contract review:

- A two-column drag-and-drop upload flow derives the document title from the baseline filename.
- Results include risk totals, severity/category filters, expandable evidence, and review controls.
- Comparison history persists through the API instead of being limited to the active browser session.
- The background uses an original, high-DPI procedural "Clause Graph" canvas. It adapts its render scale to the display, pauses in hidden tabs, and falls back to a static presentation for mobile, reduced-motion, high-contrast, and forced-colors settings.

## API summary

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/documents/{id}` | Fetch a document and its versions. |
| `POST /api/v1/documents` | Create a document and upload its first version as multipart form data. |
| `POST /api/v1/documents/{id}/versions` | Upload an additional immutable version. |
| `GET /api/v1/comparisons` | List persisted comparisons for the history view. |
| `POST /api/v1/comparisons` | Compare two versions from the same document. |
| `GET /api/v1/comparisons/{id}` | Fetch a comparison report; optionally filter by severity, category, or review status. |
| `PATCH /api/v1/changes/{id}/review` | Record a human review decision. |
| `POST /api/v1/evaluations/run` | Run the synthetic, no-key benchmark. |
| `GET /health` | Check application/database readiness. |

Example:

```json
POST /api/v1/comparisons
{
  "baseline_version_id": "<v1-id>",
  "candidate_version_id": "<v2-id>"
}
```

## Safety and scope boundaries

- Supported uploads are UTF-8 text/Markdown, text-based PDF, DOCX, and XLSX. Scanned/image-only PDFs are rejected rather than silently compared as blank text.
- An ASGI-level raw request-body limit, upload/extracted-character/section/change limits, PDF page cap, and DOCX archive-expansion cap bound the MVP's input surface.
- The core comparison is deterministic. The model receives only changed excerpts, not the complete documents.
- Optional model-backed assessment is capped at `MAX_ASSESSMENT_CALLS` per comparison (10 by default); remaining items receive an explicitly labelled heuristic budget fallback. The evaluation endpoint always uses the local heuristic provider.
- The displayed citation excerpts are generated by the backend and validated against stored source text.
- If an optional model provider fails or returns invalid output, the deterministic diff remains available through the safe heuristic fallback.
- v1 has no authentication, OCR, cloud storage, malware scanning, multi-document timelines, queues, or legal advice workflow. Do not expose a remote-provider-configured instance to the public internet without authentication, rate limiting, proxy request limits, and an isolated file-scanning/parser strategy. See [project explanation](docs/PROJECT_EXPLANATION.md#non-goals-and-scope-cuts).

## Assessment providers

| Provider | Use case | Cost |
|---|---|---|
| `heuristic` (default) | Offline demo, CI, local development | Free |
| `ollama` | Local, schema-constrained assessment with no API key | Free; uses local CPU/RAM/disk |
| `openai` | Optional structured assessment of changed sections | API usage only for changed sections |

### Use local Ollama with no API key

Install Ollama for Windows, then download/run the default model once:

```powershell
ollama run gemma3
Invoke-RestMethod http://localhost:11434/api/tags
```

For a locally run FastAPI app, set the following in `.env`, then restart the app:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=gemma3
```

For Docker Compose, leave `OLLAMA_DOCKER_BASE_URL=http://host.docker.internal:11434` in `.env`. Compose passes that host address to the app container; it does not run a model container or download a multi-GB model. The `/health` endpoint reports both the configured and active provider; a real comparison confirms that the model and selected model name are available. If Ollama is stopped, unavailable, or returns invalid structured output, ClauseLens records a labelled heuristic fallback instead of losing the deterministic report.

The native Ollama integration uses `/api/chat` with `stream: false`, a Pydantic JSON schema, and temperature `0`. It targets **local Ollama**; Ollama Cloud does not currently support structured outputs.

To use OpenAI instead, set `LLM_PROVIDER=openai`, `OPENAI_API_KEY`, and optionally `OPENAI_MODEL` in `.env`. Keep `MAX_ASSESSMENT_CALLS` low for demos (the default is `10`).

## Test and benchmark commands

```powershell
python -m ruff check .
python -m pytest -p no:cacheprovider
node --check app/static/app.js
python scripts/run_evaluation.py
```

The evaluation contains 16 synthetic document pairs and 84 labelled changes. It is a pipeline smoke benchmark, not a legal-accuracy claim. Current no-key baseline results are recorded in [verification notes](docs/VERIFICATION.md).

## Project structure

```text
app/
  api/                 # FastAPI schemas and routes
  services/            # Extraction, sectioning, diffing, assessment, evaluation
  static/              # Browser review workspace and adaptive visual background
  models.py            # SQLAlchemy entities
  main.py              # App factory and health endpoint
alembic/               # Database migration entry point
data/sample/           # Safe demo document versions
docs/                  # Project narrative, technology guide, verification record
scripts/run_evaluation.py
tests/
```

## Repository checklist

- [x] Clean standalone project structure
- [x] `.gitignore`, `.env.example`, Docker, Alembic, and MIT license
- [x] Unit/integration tests and GitHub Actions CI
- [x] Safe sample documents and no-key demo mode
- [x] Architecture, learning, and verification documentation
- [x] Remote repository configured and `main` published

## Documentation

- [Project explanation from scratch](docs/PROJECT_EXPLANATION.md)
- [Technology choices, learning time, cost, and alternatives](docs/TECHNOLOGY_AND_LEARNING.md)
- [Verification loop and current results](docs/VERIFICATION.md)
- [Hands-on run, upload, and expected-results guide](docs/testing/README.md)
