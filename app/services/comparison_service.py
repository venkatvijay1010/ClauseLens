"""Use-case services: immutable versions, deterministic comparisons, and reviewer decisions."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Change,
    ChangeAssessment,
    Comparison,
    Document,
    DocumentVersion,
    EvaluationRun,
    ReviewDecision,
    ReviewStatus,
    Section,
)
from app.services.assessment import SafeAssessmentService
from app.services.citation import change_evidence_is_valid
from app.services.diff_engine import build_diff, evidence_excerpts
from app.services.document_parser import normalize_text
from app.services.sectioning import SectionLimitError, split_into_sections


class NotFoundError(LookupError):
    pass


class InvalidComparisonError(ValueError):
    pass


@dataclass(frozen=True)
class VersionInput:
    version_label: str
    content: str
    original_filename: str | None = None


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _create_sections(
    db: Session, version: DocumentVersion, raw_text: str, max_sections_per_version: int
) -> None:
    try:
        parsed_sections = split_into_sections(raw_text, max_sections=max_sections_per_version)
    except SectionLimitError as exc:
        raise ValueError(str(exc)) from exc
    for parsed in parsed_sections:
        db.add(
            Section(
                version_id=version.id,
                ordinal=parsed.ordinal,
                heading=parsed.heading,
                normalized_heading=parsed.normalized_heading,
                content=parsed.content,
                page_number=parsed.page_number,
            )
        )


def create_document(
    db: Session, title: str, version_input: VersionInput, max_sections_per_version: int = 250
) -> Document:
    raw_text = version_input.content.strip()
    normalized = normalize_text(raw_text)
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("Document title cannot be blank.")
    if not normalized:
        raise ValueError("Document content cannot be empty.")
    document = Document(title=normalized_title)
    db.add(document)
    db.flush()
    create_version(db, document.id, version_input, max_sections_per_version)
    db.flush()
    return document


def create_version(
    db: Session, document_id: str, version_input: VersionInput, max_sections_per_version: int = 250
) -> DocumentVersion:
    document = db.get(Document, document_id)
    if not document:
        raise NotFoundError("Document not found.")
    raw_text = version_input.content.strip()
    normalized = normalize_text(raw_text)
    normalized_label = version_input.version_label.strip()
    if not normalized_label:
        raise ValueError("Version label cannot be blank.")
    if not normalized:
        raise ValueError("Document content cannot be empty.")
    version = DocumentVersion(
        document_id=document_id,
        version_label=normalized_label,
        original_filename=version_input.original_filename,
        content_hash=_hash_text(raw_text),
        raw_text=raw_text,
        normalized_text=normalized,
        extracted_character_count=len(normalized),
    )
    db.add(version)
    db.flush()
    _create_sections(db, version, raw_text, max_sections_per_version)
    db.flush()
    return version


def _get_version(db: Session, version_id: str) -> DocumentVersion:
    version = db.scalar(
        select(DocumentVersion)
        .options(selectinload(DocumentVersion.sections), selectinload(DocumentVersion.document))
        .where(DocumentVersion.id == version_id)
    )
    if not version:
        raise NotFoundError("Document version not found.")
    return version


def create_or_get_comparison(
    db: Session,
    baseline_version_id: str,
    candidate_version_id: str,
    assessment_service: SafeAssessmentService,
    max_changed_sections: int,
    max_assessment_calls: int,
) -> Comparison:
    if baseline_version_id == candidate_version_id:
        raise InvalidComparisonError("Choose two different versions to compare.")
    baseline = _get_version(db, baseline_version_id)
    candidate = _get_version(db, candidate_version_id)
    if baseline.document_id != candidate.document_id:
        raise InvalidComparisonError("Versions must belong to the same document.")

    existing = db.scalar(
        select(Comparison)
        .options(
            selectinload(Comparison.changes).selectinload(Change.assessment),
            selectinload(Comparison.changes).selectinload(Change.review_decisions),
        )
        .where(
            Comparison.baseline_version_id == baseline_version_id,
            Comparison.candidate_version_id == candidate_version_id,
        )
    )
    if existing:
        return existing

    start = time.perf_counter()
    candidates = build_diff(baseline.sections, candidate.sections)
    if len(candidates) > max_changed_sections:
        raise InvalidComparisonError(
            f"Comparison has {len(candidates)} changed sections, above the {max_changed_sections} safety limit."
        )

    comparison = Comparison(
        baseline_version_id=baseline_version_id,
        candidate_version_id=candidate_version_id,
        status="completed",
    )
    db.add(comparison)
    db.flush()
    remote_assessment_calls = 0
    for display_order, candidate_diff in enumerate(candidates, 1):
        old_text = candidate_diff.baseline.content if candidate_diff.baseline else None
        new_text = candidate_diff.candidate.content if candidate_diff.candidate else None
        old_excerpt, new_excerpt = evidence_excerpts(old_text, new_text)
        change = Change(
            comparison_id=comparison.id,
            baseline_section_id=candidate_diff.baseline.id if candidate_diff.baseline else None,
            candidate_section_id=candidate_diff.candidate.id if candidate_diff.candidate else None,
            display_order=display_order,
            change_type=candidate_diff.change_type.value,
            old_heading=candidate_diff.baseline.heading if candidate_diff.baseline else None,
            new_heading=candidate_diff.candidate.heading if candidate_diff.candidate else None,
            old_page_number=candidate_diff.baseline.page_number if candidate_diff.baseline else None,
            new_page_number=candidate_diff.candidate.page_number if candidate_diff.candidate else None,
            old_text=old_text,
            new_text=new_text,
            old_excerpt=old_excerpt,
            new_excerpt=new_excerpt,
            similarity=candidate_diff.similarity,
        )
        db.add(change)
        db.flush()
        if assessment_service.uses_remote_provider and remote_assessment_calls >= max_assessment_calls:
            result = assessment_service.fallback_assessment(
                candidate_diff.change_type, candidate_diff.heading, old_excerpt, new_excerpt
            )
        else:
            result = assessment_service.assess(
                candidate_diff.change_type, candidate_diff.heading, old_excerpt, new_excerpt
            )
            if assessment_service.uses_remote_provider:
                remote_assessment_calls += 1
        evidence_valid = change_evidence_is_valid(
            change.old_text, change.old_excerpt, change.new_text, change.new_excerpt
        )
        db.add(
            ChangeAssessment(
                change_id=change.id,
                category=result.payload.category.value,
                severity=result.payload.severity.value,
                summary=result.payload.summary,
                rationale=result.payload.rationale,
                needs_human_review=result.payload.needs_human_review or not evidence_valid,
                provider=result.provider,
                validation_status=result.validation_status if evidence_valid else "citation_validation_failed",
            )
        )
        db.add(ReviewDecision(change_id=change.id, sequence=0, status=ReviewStatus.PENDING.value, note=None))
    comparison.duration_ms = int((time.perf_counter() - start) * 1000)
    db.flush()
    return comparison


def get_comparison(db: Session, comparison_id: str) -> Comparison:
    comparison = db.scalar(
        select(Comparison)
        .options(
            selectinload(Comparison.changes).selectinload(Change.assessment),
            selectinload(Comparison.changes).selectinload(Change.review_decisions),
        )
        .where(Comparison.id == comparison_id)
    )
    if not comparison:
        raise NotFoundError("Comparison not found.")
    return comparison


def add_review_decision(db: Session, change_id: str, status: ReviewStatus, note: str | None) -> ReviewDecision:
    change = db.get(Change, change_id)
    if not change:
        raise NotFoundError("Change not found.")
    current_sequence = db.scalar(
        select(func.max(ReviewDecision.sequence)).where(ReviewDecision.change_id == change_id)
    )
    decision = ReviewDecision(
        change_id=change_id,
        sequence=(current_sequence or 0) + 1,
        status=status.value,
        note=note.strip() if note else None,
    )
    db.add(decision)
    db.flush()
    return decision


def store_evaluation_run(db: Session, provider: str, case_count: int, metrics_json: str) -> EvaluationRun:
    run = EvaluationRun(provider=provider, case_count=case_count, metrics_json=metrics_json)
    db.add(run)
    db.flush()
    return run
