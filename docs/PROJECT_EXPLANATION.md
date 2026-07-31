# ClauseLens: project explanation from scratch

## 1. Problem

Document changes are easy to make and hard to review. A raw redline shows that text moved or changed, but it does not help a reviewer quickly identify the changes most likely to affect payment, privacy, termination rights, deadlines, or customer obligations.

ClauseLens is a small, production-minded change-review assistant. A reviewer supplies a baseline and revised version of the same document. The application identifies added, removed, modified, and moved sections, ranks their likely significance, and shows exact before/after evidence.

It is designed for neutral document types such as SaaS terms, privacy notices, vendor agreements, and employee handbooks. It intentionally does not claim legal or compliance correctness.

## 2. Target users and user journey

Primary users are operations, procurement, compliance, HR, or product reviewers who need a reliable first pass before human approval.

1. The reviewer creates a document and uploads or pastes version `v1`.
2. The reviewer adds `v2` to the same document record.
3. The reviewer creates a comparison.
4. ClauseLens calculates a deterministic change set, then sends only changed excerpts to an assessment provider.
5. The reviewer filters high-severity or privacy-related changes, reads exact before/after excerpts, and records a review decision.

The most important trust property is that the evidence comes from the stored versions, not from model-generated quotations.

## 3. Product boundary

ClauseLens is not:

- a general document chatbot;
- a RAG answer engine;
- a text-to-SQL tool;
- a multi-agent system;
- a document editor or PDF-redlining tool;
- legal advice or an automated approval engine.

Keeping this boundary makes the project finishable in 2–4 weeks and keeps the review workflow focused.

## 4. End-to-end architecture

```text
Document v1 + Document v2
        |
        v
File/text extraction and lightweight normalization
        |
        v
Heading-aware section splitter with page anchors
        |
        v
Exact title alignment -> conservative fuzzy-title fallback
        |
        v
Deterministic section-level and text-level comparison
        |
        v
Structured assessment for changed sections only
        |
        v
Pydantic validation + deterministic source-excerpt validation
        |
        v
PostgreSQL comparison report, REST API, and browser review screen
```

The system is intentionally a straightforward pipeline. It has no agent supervisor, no routing graph, and no background orchestration service.

## 5. Deterministic work versus LLM work

The deterministic layer owns facts:

- file-format validation;
- section splitting;
- section alignment;
- determining whether text changed;
- extracting source excerpts;
- validating citations;
- enforcing limits and persistence.

The assessment layer only adds a constrained interpretation:

- category: deadline, payment, privacy, obligation, termination, eligibility, or other;
- severity: low, medium, or high;
- concise summary and rationale;
- whether human review is needed.

This choice reduces cost, makes test results reproducible, and prevents a model from inventing that a text change exists. The optional provider can be a local Ollama model with no API key or a remote OpenAI model. If it fails, a local deterministic assessment fallback still returns a usable report.

## 6. Data model

| Entity | Responsibility |
|---|---|
| `documents` | Stable logical record for one document. |
| `document_versions` | Immutable source text, hash, label, and metadata. |
| `sections` | Heading-aware text regions with source order/page anchors. |
| `comparisons` | Idempotent baseline/candidate comparison job/report. |
| `changes` | Deterministic added, removed, modified, or moved evidence. |
| `change_assessments` | Structured AI/fallback assessment tied to a change. |
| `review_decisions` | Human review status and note history. |
| `evaluation_runs` | Reproducible benchmark metadata and metrics. |

## 7. Evidence and safety model

Each change keeps the old/new source text, excerpt, source section, and associated version IDs. Before an assessment is persisted, the backend verifies that each excerpt maps to the source text after only whitespace normalization. The UI never relies on an LLM-supplied quotation or offset.

MVP safety controls include an ASGI-level request-body limit, file/character/section/change-count limits, a PDF page cap, a DOCX archive-expansion cap, and rejection of unsupported, encrypted, malformed, or empty-text documents. Optional model-backed assessment is capped at 10 calls per comparison by default; any remaining change receives a labelled local fallback, and the benchmark never calls a model provider. Local Ollama keeps the changed excerpts on the developer machine; a remote provider requires a separate privacy review. Uploaded document text should be treated as sensitive. The demo has no authentication; a real deployment would add identity, access control, encryption/storage policy, malware scanning, retention/deletion, a reverse-proxy body limit, isolated file parsing, rate limiting, and vendor privacy review.

## 8. Evaluation approach

The checked-in benchmark produces 16 synthetic document pairs with 84 labelled changes. It measures:

- change-detection precision, recall, and F1;
- section-alignment accuracy;
- severity macro-F1;
- citation validity;
- structured-output/fallback validity;
- p50 and p95 processing time.

This validates the deterministic pipeline and no-key fallback. It does **not** establish legal correctness or production model quality. A stronger later iteration would add 15–20 manually reviewed, clearly licensed/public document pairs and compare a real model provider against human labels.

## 9. How it differs from a RAG project like PolicyMind

PolicyMind accepts a question, retrieves policy chunks with hybrid vector/BM25 search, and may route to a SQL or hybrid agent. Its output is an answer with citations.

ClauseLens has a different input, control flow, output, and benchmark:

| Dimension | PolicyMind | ClauseLens |
|---|---|---|
| Input | Natural-language question | Version `v1` and `v2` of one document |
| Core task | Answer grounded questions | Detect and prioritize text changes |
| Main AI pattern | Retrieval/SQL routing and answer synthesis | Structured interpretation after deterministic diff |
| Retrieval | Hybrid pgvector + BM25 | Not required in MVP |
| Database | Policies, chunks, claims data | Versions, sections, changes, review decisions |
| Evaluation | Answer/retrieval quality | Detection, alignment, severity, evidence validity |

They share healthy backend fundamentals—FastAPI, PostgreSQL, Docker, testing, and citations—but they do not repeat the same AI product.

## 10. Non-goals and scope cuts

The following are deliberately excluded from v1: OCR, scanned PDFs, cloud file connectors, authentication, teams/comments/notifications, multilingual models, unlimited document size, multi-version timelines, native redline export, automatic legal approval, external regulation lookup, queues, and vector search.

pgvector can be added only after the core flow is stable for a small feature such as: “show previously reviewed, similar changes and their human decisions.” It should not turn ClauseLens into another RAG product.

## 11. Delivery plan and definition of done

Estimated effort is 50–60 focused hours, plus 8–10 hours of buffer. At 14–18 hours each week, this is a 3–4 week project.

Definition of done:

1. A reviewer can run `docker compose up --build` with no paid API key.
2. The browser demo compares the included sample versions.
3. The API stores versions, a comparison, assessments, and review decisions in PostgreSQL.
4. Every displayed source excerpt is validated.
5. Tests, lint, and the synthetic benchmark pass.
6. The README explains setup, architecture, limitations, and metrics in under five minutes of reading.
