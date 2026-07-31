# ClauseLens testing kit

This folder is a practical guide for running ClauseLens, uploading safe sample documents, and checking the report you receive.

Use the default heuristic provider while following this kit. It is free, needs no API key or model download, and makes the expected categories and severities reproducible.

## Start here

1. Follow [RUN_PROJECT.md](RUN_PROJECT.md) to start the app with Docker or local Python.
2. Read [UPLOAD_FILES.md](UPLOAD_FILES.md) to choose between the paste-only browser demo and the file-upload API.
3. Upload one of the pairs in [fixtures](fixtures).
4. Compare your result with [EXPECTED_RESULTS.md](EXPECTED_RESULTS.md).
5. If something does not work, use [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Included fixture pairs

| Pair | What it demonstrates | Expected number of changes |
|---|---|---:|
| 01_high_risk | Payment, privacy, and termination changes | 3 |
| 02_structure_deadline | Modified, added, and moved sections | 4 |
| 03_lifecycle | Modified, removed, moved, and added sections | 4 |

The fixture documents are fictional and safe to upload. They are Markdown files so they exercise the same heading-aware extraction path as a real text document.

## Important limits of this guide

- The browser screen accepts pasted text only. It has no file-picker control.
- File uploads are available through Swagger at http://localhost:8001/docs when using Docker, or http://localhost:8000/docs for a local Python run.
- Upload the baseline and revised files as two versions of the same document. Do not create two separate documents, because ClauseLens intentionally rejects cross-document comparisons.
- Do not upload confidential, personal, or legally sensitive documents to this unauthenticated demo. ClauseLens stores extracted text and the original filename in the configured database. It does not persist the original uploaded binary file.
