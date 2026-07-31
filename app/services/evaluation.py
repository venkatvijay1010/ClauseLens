"""Reproducible synthetic benchmark for deterministic flow and assessment plumbing."""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass

from app.models import ChangeType, Severity
from app.services.assessment import SafeAssessmentService
from app.services.citation import change_evidence_is_valid
from app.services.diff_engine import build_diff, excerpt
from app.services.sectioning import split_into_sections


@dataclass(frozen=True)
class EvaluationCase:
    name: str
    baseline_text: str
    candidate_text: str
    expected: dict[tuple[str, ChangeType], Severity]


def _document(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"{index}. {heading}\n{text}" for index, (heading, text) in enumerate(sections, 1))


def build_evaluation_cases() -> list[EvaluationCase]:
    """Create 16 deterministic, labelled pairs with five labelled changes each.

    These are synthetic smoke/benchmark cases, not evidence of legal-model accuracy.
    """
    cases: list[EvaluationCase] = []
    for index in range(1, 17):
        base_sections = [
            ("Service Scope", "The provider will supply the standard hosted service."),
            ("Payment Terms", f"The customer will pay ${100 + index} within 30 days of invoice."),
            ("Privacy and Data Use", "The provider uses personal data only to deliver the service."),
            ("Notice Period", "Either party must provide 30 days written notice."),
            ("Termination", "Either party may terminate for material breach after notice."),
            ("General Language", "Headings are provided for convenience only."),
        ]
        candidate_sections = [
            ("Service Scope", "The provider will supply the standard hosted service."),
            ("Payment Terms", f"The customer will pay ${200 + index} within 15 days of invoice."),
            (
                "Privacy and Data Use",
                "The provider may share personal data with approved analytics subprocessors.",
            ),
            ("Notice Period", "Either party must provide 10 business days written notice."),
            ("Termination", "The provider may terminate immediately for convenience."),
            ("General Language", "Section headings are for convenient reference only."),
        ]
        expected: dict[tuple[str, ChangeType], Severity] = {
            ("Payment Terms", ChangeType.MODIFIED): Severity.HIGH,
            ("Privacy And Data Use", ChangeType.MODIFIED): Severity.HIGH,
            ("Notice Period", ChangeType.MODIFIED): Severity.MEDIUM,
            ("Termination", ChangeType.MODIFIED): Severity.HIGH,
            ("General Language", ChangeType.MODIFIED): Severity.LOW,
        }
        if index % 4 == 0:
            candidate_sections.append(("Eligibility", "Only verified business customers are eligible."))
            expected[("Eligibility", ChangeType.ADDED)] = Severity.MEDIUM
        if index % 5 == 0:
            candidate_sections = [item for item in candidate_sections if item[0] != "General Language"]
            expected.pop(("General Language", ChangeType.MODIFIED))
            expected[("General Language", ChangeType.REMOVED)] = Severity.LOW
        cases.append(
            EvaluationCase(
                name=f"synthetic_terms_{index:02d}",
                baseline_text=_document(base_sections),
                candidate_text=_document(candidate_sections),
                expected=expected,
            )
        )
    return cases


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower, upper = int(position), min(int(position) + 1, len(ordered) - 1)
    fraction = position - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction, 2)


def _macro_f1(truth: list[str], prediction: list[str]) -> float:
    labels = [severity.value for severity in Severity]
    scores: list[float] = []
    for label in labels:
        tp = sum(actual == label and predicted == label for actual, predicted in zip(truth, prediction))
        fp = sum(actual != label and predicted == label for actual, predicted in zip(truth, prediction))
        fn = sum(actual == label and predicted != label for actual, predicted in zip(truth, prediction))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * precision * recall / (precision + recall) if precision + recall else 0.0)
    return round(sum(scores) / len(scores), 4)


def run_benchmark(assessment_service: SafeAssessmentService) -> dict[str, object]:
    cases = build_evaluation_cases()
    expected_count = 0
    predicted_count = 0
    true_positives = 0
    alignment_correct = 0
    alignment_total = 0
    citation_valid = 0
    structured_valid = 0
    durations_ms: list[float] = []
    severity_truth: list[str] = []
    severity_predictions: list[str] = []

    for case in cases:
        start = time.perf_counter()
        baseline = split_into_sections(case.baseline_text)
        candidate = split_into_sections(case.candidate_text)
        changes = build_diff(baseline, candidate)
        durations_ms.append((time.perf_counter() - start) * 1000)
        predicted_count += len(changes)

        predicted_lookup = {(item.heading.title(), item.change_type): item for item in changes}
        expected_count += len(case.expected)
        for key, expected_severity in case.expected.items():
            actual = predicted_lookup.get(key)
            if not actual:
                continue
            true_positives += 1
            if actual.baseline and actual.candidate:
                alignment_total += 1
                if actual.baseline.normalized_heading == actual.candidate.normalized_heading:
                    alignment_correct += 1
            result = assessment_service.assess(
                actual.change_type,
                actual.heading,
                actual.baseline.content if actual.baseline else None,
                actual.candidate.content if actual.candidate else None,
            )
            if result.validation_status.startswith("validated") or result.validation_status.startswith("fallback"):
                structured_valid += 1
            if change_evidence_is_valid(
                actual.baseline.content if actual.baseline else None,
                excerpt(actual.baseline.content if actual.baseline else None),
                actual.candidate.content if actual.candidate else None,
                excerpt(actual.candidate.content if actual.candidate else None),
            ):
                citation_valid += 1
            severity_truth.append(expected_severity.value)
            severity_predictions.append(result.payload.severity.value)

    precision = true_positives / predicted_count if predicted_count else 0.0
    recall = true_positives / expected_count if expected_count else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    matched = len(severity_truth)
    return {
        "benchmark_type": "synthetic deterministic smoke benchmark",
        "case_count": len(cases),
        "labelled_change_count": expected_count,
        "change_detection": {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        },
        "section_alignment_accuracy": round(alignment_correct / alignment_total, 4)
        if alignment_total
        else 0.0,
        "severity_macro_f1": _macro_f1(severity_truth, severity_predictions) if matched else 0.0,
        "citation_validity_rate": round(citation_valid / matched, 4) if matched else 0.0,
        "structured_output_validity_rate": round(structured_valid / matched, 4) if matched else 0.0,
        "latency_ms": {
            "p50": _percentile(durations_ms, 0.50),
            "p95": _percentile(durations_ms, 0.95),
            "mean": round(statistics.mean(durations_ms), 2) if durations_ms else 0.0,
        },
        "limitations": [
            "Synthetic cases validate the pipeline, not legal correctness.",
            "The default heuristic provider is a no-key fallback, not a replacement for human review.",
        ],
    }
