# Verification loop and current baseline

DocuDiff was checked with the following repeatable loop:

```text
implementation review
  -> unit/integration tests
  -> lint
  -> synthetic benchmark
  -> inspect evidence/fallback behavior
  -> repair findings
  -> repeat
```

## Current local results

Run from the repository root:

```powershell
python -m ruff check .
python -m pytest -p no:cacheprovider
python scripts/run_evaluation.py
```

Latest validation during initial project creation:

| Check | Result |
|---|---|
| Python syntax compilation | Passed |
| Unit/integration tests | 19 passed |
| Ruff lint | Passed |
| Synthetic cases | 16 |
| Labelled changes | 84 |
| Change detection precision / recall / F1 | 1.00 / 1.00 / 1.00 |
| Section alignment accuracy | 1.00 |
| Heuristic severity macro-F1 | 1.00 |
| Citation validity | 1.00 |
| Structured/fallback validity | 1.00 |

The benchmark is intentionally synthetic and deterministic. These values demonstrate pipeline integrity and should not be represented as a legal-domain or real-model quality claim.

## Explicitly checked invariants

- A document must have non-empty extracted text.
- A comparison must contain two different versions of the same document.
- Exact heading alignment runs before conservative fuzzy alignment.
- A moved unchanged section is not misreported as an added/removed pair.
- The deterministic diff remains usable if an assessment provider fails.
- Every displayed old/new excerpt is validated against stored source text.
- No paid API key is required for the browser demo, test suite, or benchmark.
- Scanned/image-only PDFs are explicitly out of scope for v1.
- Raw HTTP body limits are enforced before multipart parsing, and DOCX archive expansion is bounded before document parsing.
- Large unmatched section sets skip fuzzy alignment; document versions also have a hard section-count limit.
- Remote assessment calls are bounded per comparison; the benchmark is always local/heuristic.

## Remaining manual release check

Before publishing to GitHub, run the Docker quick-start on a machine with Docker Desktop available and confirm:

1. `docker compose up --build` starts PostgreSQL and the FastAPI app;
2. `GET /health` returns `200`;
3. the browser demo completes a comparison;
4. data remains after a container restart.

That check is deliberately recorded separately because it requires a local Docker daemon and image pulls, which may not be available in every coding environment.
