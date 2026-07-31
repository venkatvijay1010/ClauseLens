# Expected results

## Conditions for reproducible results

The tables below are verified against the default setting:

~~~text
LLM_PROVIDER=heuristic
~~~

With this provider, the document alignment, change types, categories, severities, validation status, and starting review state are deterministic. UUIDs, timestamps, duration_ms, and exact similarity numbers vary between runs.

Ollama and external providers do not change the deterministic diff, section headings, or source excerpts. Their category, severity, and wording can differ from the heuristic results below.

## 01_high_risk

Upload fixtures/01_high_risk_baseline.md as v1 and fixtures/01_high_risk_revised.md as v2.

Expected report: 3 changes, all modified, high severity, validated, and pending review.

| Heading | Change type | Category | Severity | Needs human review |
|---|---|---|---|---|
| Payment Terms | modified | payment | high | yes |
| Privacy and Data Use | modified | privacy | high | yes |
| Termination | modified | termination | high | yes |

In the browser demo, you should see the text 3 change(s) found followed by three high and modified result cards.

## 02_structure_deadline

Upload fixtures/02_structure_deadline_baseline.md as v1 and fixtures/02_structure_deadline_revised.md as v2.

Expected report: 4 changes.

| Heading | Change type | Category | Severity | Needs human review |
|---|---|---|---|---|
| Scope | moved | other | low | no |
| Account Access | moved | eligibility | low | no |
| Implementation Schedule | modified | deadline | medium | yes |
| Data Retention | added | privacy | high | yes |

This pair proves that ClauseLens can distinguish a reordered, unchanged section from a modified or newly added section.

## 03_lifecycle

Upload fixtures/03_lifecycle_baseline.md as v1 and fixtures/03_lifecycle_revised.md as v2.

Expected report: 4 changes.

| Heading | Change type | Category | Severity | Needs human review |
|---|---|---|---|---|
| Renewal | removed | termination | high | yes |
| Refunds | modified | payment | high | yes |
| Support | moved | other | low | no |
| Data Sharing | added | privacy | high | yes |

This pair covers every supported change type: modified, removed, moved, and added.

## What a valid API item looks like

The exact IDs and excerpts will vary, but an item from the first pair should have this shape:

~~~json
{
  "change_type": "modified",
  "old_heading": "Payment Terms",
  "new_heading": "Payment Terms",
  "assessment": {
    "category": "payment",
    "severity": "high",
    "provider": "heuristic",
    "validation_status": "validated"
  },
  "latest_review": {
    "status": "pending"
  }
}
~~~

The old_excerpt and new_excerpt fields must be recognisable, contiguous text from the two source versions. They are not model-written quotations.

## Optional endpoint-level smoke check

POST /api/v1/evaluations/run runs the built-in synthetic benchmark. With the heuristic provider it should return:

- case_count: 16
- labelled_change_count: 84
- change_detection precision, recall, and f1: 1.0
- section_alignment_accuracy: 1.0
- severity_macro_f1: 1.0
- citation_validity_rate: 1.0
- structured_output_validity_rate: 1.0

The endpoint records an evaluation result in the database. It does not make a legal-accuracy claim.
