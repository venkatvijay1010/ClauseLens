# Upload and compare documents

## What to prepare

Prepare two versions of the same logical document:

1. A baseline version, usually labelled v1.
2. A revised version, usually labelled v2.

Keep equivalent headings stable between versions whenever possible. ClauseLens aligns sections by exact heading first, then uses a conservative fuzzy-heading fallback. Markdown headings, conventional numbered headings such as 1. Payment Terms, and short ALL-CAPS headings work best.

## Supported inputs and default limits

| Item | Supported behavior |
|---|---|
| File types | .txt, .md, text-based .pdf, and .docx |
| Text encoding | .txt and .md must be UTF-8 |
| Raw upload size | 5 MiB per upload |
| Extracted text | 500,000 characters per version |
| Document structure | 250 sections per version |
| Comparison result | 100 detected changed sections |
| PDF | Text-based, unencrypted, and 500 pages or fewer |
| DOCX | Subject to archive-expansion safety checks |

Do not use scanned or image-only PDFs, encrypted PDFs, .doc files, spreadsheets, images, or archives. The v1 service does not run OCR.

## Fastest check: paste into the browser demo

The browser demo is for pasted text, not file uploads.

1. Start the app using [RUN_PROJECT.md](RUN_PROJECT.md).
2. Open the browser demo URL shown there.
3. Open fixtures/01_high_risk_baseline.md in an editor and paste its complete contents into Baseline - v1.
4. Open fixtures/01_high_risk_revised.md and paste its complete contents into Revised - v2.
5. Enter a title such as High Risk Terms.
6. Select Run comparison.
7. Check the three result cards against [EXPECTED_RESULTS.md](EXPECTED_RESULTS.md).

This route is ideal for understanding the report. It does not exercise PDF, DOCX, or multipart file extraction.

## File upload walkthrough in Swagger

Use this route when you want to upload the fixture files themselves.

1. Start ClauseLens and open the API documentation endpoint:
   - Docker: http://localhost:8001/docs
   - Local Python: http://localhost:8000/docs
2. Expand POST /api/v1/documents/upload and select Try it out.
3. Fill the form:
   - title: High Risk Terms
   - version_label: v1
   - file: select fixtures/01_high_risk_baseline.md
4. Select Execute. In the JSON response, save:
   - id as the document ID
   - versions[0].id as the baseline version ID
5. Expand POST /api/v1/documents/{document_id}/versions/upload and select Try it out.
6. Enter the document ID from step 4, set version_label to v2, and select fixtures/01_high_risk_revised.md.
7. Select Execute and save the returned id as the candidate version ID.
8. Expand POST /api/v1/comparisons, select Try it out, and submit:

~~~json
{
  "baseline_version_id": "<baseline version ID>",
  "candidate_version_id": "<candidate version ID>"
}
~~~

9. The response is the comparison report. Its changes array contains the deterministic change type, evidence excerpts, assessment, and initial review state.
10. To reload the report later, use GET /api/v1/comparisons/{comparison_id}.

## Review a result

Every change begins with review status pending. To record your decision:

1. Copy a change id from the comparison response.
2. Open PATCH /api/v1/changes/{change_id}/review in Swagger.
3. Use reviewed or dismissed and optionally add a note.
4. Fetch the comparison again to see latest_review updated.

## Data handling

ClauseLens extracts and stores text plus the original filename in the database. It does not currently retain the binary file in uploads. Treat all uploaded text as sensitive.

The default heuristic provider stays local. When using Ollama, changed excerpts stay on the machine running Ollama. When using an external provider, changed excerpts are sent to that provider; review the provider and your data policy before using real documents.
