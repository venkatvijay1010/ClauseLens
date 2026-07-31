# Technology choices, learning time, cost, and trade-offs

## How to read the time estimates

These are **incremental learning estimates** for a backend engineer with roughly 1–1.5 years of experience. They overlap: do not add every row and conclude that the project requires 60+ hours of study before coding. Learn each topic while building its milestone, then reserve 50–60 total focused project hours for implementation, debugging, tests, demo polish, and documentation.

| Technology / concept | Why it is used in ClauseLens | Incremental learning time | Difficulty | Typical local cost | Alternative considered / why not in v1 |
|---|---|---:|---|---|---|
| Python 3.11+ | Familiar, productive backend language and strong document/AI ecosystem | 0–2h if already using Python | Low | Free | Node/Java would work, but add unnecessary switching cost. |
| FastAPI + Pydantic | Typed request/response contracts, validation, interactive API docs | 4–8h | Low–Medium | Free | Flask has less built-in schema ergonomics; Django is heavier than needed. |
| PostgreSQL | Stores version history, changes, assessments, and review decisions | 3–5h | Medium | Free in Docker | SQLite is used only for fast tests; PostgreSQL is the portfolio deployment path. |
| SQLAlchemy 2.0 | Keeps database code structured and testable | 3–5h | Medium | Free | Raw SQL is smaller at first but makes relationships/migrations less maintainable. |
| Alembic | Gives the repository a migration story for clean database setup | 2–4h | Medium | Free | `create_all()` alone is less credible for schema evolution. |
| Docker Compose | Runs app and PostgreSQL consistently for demos and GitHub cloning | 4–6h | Medium | Free locally | Cloud deployment is intentionally optional, not a v1 task. |
| `pypdf` + `python-docx` | Extracts text from common text-native document formats | 3–5h | Medium | Free | OCR is intentionally excluded because it adds accuracy, privacy, and infrastructure risk. |
| Heading-aware parsing | Preserves useful document structure before diffing | 3–5h | Medium | Free | Chunking by fixed tokens would look too similar to RAG and produces poor diffs. |
| `difflib.SequenceMatcher` | Deterministic section/title matching and text similarity | 3–5h | Medium | Free | An embedding matcher is unnecessary before proving simple rules work. |
| Ollama + local structured output | Runs an optional local model through a schema-constrained API without an API key | 1–3h | Low–Medium | Free; consumes local CPU/RAM/disk | A hosted API is simpler to deploy but is not needed for the core demo. |
| Structured LLM outputs | Produces constrained category/severity/reasoning fields only after diffing | 4–8h | Medium | Low, based on changed excerpts | Free heuristic fallback is included for CI/demo; unconstrained chat output was rejected. |
| Pydantic + citation validation | Rejects malformed model output and unverified evidence | 2–4h | Medium | Free | Trusting model-supplied quotes would weaken the main reliability claim. |
| Vanilla JS/CSS demo UI | Lets a recruiter run a real comparison without learning the API first | 4–8h | Low–Medium | Free | React is a valid future upgrade, but a small UI is more realistic for this timeline. |
| Pytest, Ruff, GitHub Actions | Proves deterministic logic, endpoint lifecycle, and code health | 8–12h | Medium | Free on public GitHub repositories | Manual testing alone is insufficient for a backend/AI portfolio project. |
| Evaluation design | Shows measurable performance rather than a subjective demo | 5–8h | Medium | Free for synthetic benchmark | RAGAS/LLM-as-a-judge would add a different project’s complexity. |

## Recommended learning/build order

1. **Foundation:** FastAPI, Pydantic, PostgreSQL, SQLAlchemy, and Docker.
2. **Core product logic:** document extraction, normalization, section splitting, exact/fuzzy title matching, deterministic diffs.
3. **Trust layer:** source excerpts, citation validation, error/fallback handling.
4. **AI layer:** structured assessment only after deterministic changes work.
5. **Portfolio proof:** test suite, synthetic benchmark, browser demo, README, and video.

This order matters. The project remains useful even if no external LLM key is configured.

## Cost factors

| Factor | v1 decision | Impact |
|---|---|---|
| Local development | Docker + heuristic provider, or FastAPI + local Ollama | Free except local machine resources. |
| LLM calls | Send changed excerpts only; cap model calls at 10 per comparison and fall back locally afterward | Keeps demo cost and latency bounded. |
| Database | Local PostgreSQL container | Free. |
| File storage | Store text/content locally in demo | Free, but not production-grade. |
| Hosting | Optional after the local demo works | Avoids premature cloud cost. |

The MVP implements a per-comparison model-call budget, maximum change count, and request timeout. Before public use with a remote provider, add dashboard logging, authentication/rate limits, and a spend alert as well.

## Design decisions worth discussing in interviews

### Why diff before the LLM?

The deterministic diff proves what changed and reduces the LLM context to only relevant excerpts. This improves cost, latency, reproducibility, and evidence quality.

### Why not build a multi-agent workflow?

There is no independent task requiring an autonomous planner or supervisor. A simple pipeline is easier to test and more credible for the product scope.

### Why not add vector search first?

The user needs comparison, not retrieval. Vector search is a later enhancement for finding historic precedent; adding it to the MVP would blur ClauseLens’s distinction from a RAG application.

### Why retain a heuristic provider?

It lets the repository, automated tests, demo, and evaluator run without secrets or paid API access. It also proves that a provider outage does not erase deterministic results.

## Interview-ready technology summary

> “I built ClauseLens with FastAPI, PostgreSQL, SQLAlchemy, and Docker. The backend preserves immutable document versions, aligns their sections deterministically, and computes the diff before it asks a provider for a structured impact assessment. I can run the provider locally with Ollama and no API key, while retaining a deterministic fallback. I validate each displayed excerpt against stored source text, so the model cannot invent evidence.”
