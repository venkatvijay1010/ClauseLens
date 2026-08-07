"""Versioned HTTP API for ClauseLens."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.schemas import (
    AssessmentResponse,
    ChangeResponse,
    ComparisonCreateRequest,
    ComparisonResponse,
    DocumentResponse,
    EvaluationResponse,
    ReviewRequest,
    ReviewResponse,
    VersionResponse,
)
from app.models import (
    Change,
    ChangeCategory,
    Comparison,
    Document,
    DocumentVersion,
    ReviewStatus,
    Severity,
)
from app.services.assessment import HeuristicAssessmentProvider, SafeAssessmentService
from app.services.comparison_service import (
    InvalidComparisonError,
    NotFoundError,
    VersionInput,
    add_review_decision,
    create_document,
    create_or_get_comparison,
    create_version,
    get_comparison,
    store_evaluation_run,
)
from app.services.document_parser import DocumentExtractionError, extract_document
from app.services.evaluation import run_benchmark

router = APIRouter(prefix="/api/v1", tags=["ClauseLens"])


def get_db(request: Request) -> Iterator[Session]:
    db = request.app.state.db.session_factory()
    try:
        yield db
    finally:
        db.close()


DatabaseDependency = Annotated[Session, Depends(get_db)]


async def _read_limited_upload(file: UploadFile, max_upload_bytes: int) -> bytes:
    """Read multipart content in bounded chunks instead of accepting an unbounded body in memory."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_upload_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {max_upload_bytes:,}-byte upload limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _version_response(version) -> VersionResponse:
    return VersionResponse(
        id=version.id,
        version_label=version.version_label,
        original_filename=version.original_filename,
        extracted_character_count=version.extracted_character_count,
        section_count=len(version.sections),
        created_at=version.created_at,
    )


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        title=document.title,
        versions=[_version_response(version) for version in document.versions],
    )


def _change_response(change: Change) -> ChangeResponse:
    assessment = None
    if change.assessment:
        assessment = AssessmentResponse(
            category=change.assessment.category,
            severity=change.assessment.severity,
            summary=change.assessment.summary,
            rationale=change.assessment.rationale,
            needs_human_review=change.assessment.needs_human_review,
            provider=change.assessment.provider,
            validation_status=change.assessment.validation_status,
        )
    latest_review = change.review_decisions[-1] if change.review_decisions else None
    review = None
    if latest_review:
        review = ReviewResponse(
            status=latest_review.status, note=latest_review.note, created_at=latest_review.created_at
        )
    return ChangeResponse(
        id=change.id,
        display_order=change.display_order,
        change_type=change.change_type,
        old_heading=change.old_heading,
        new_heading=change.new_heading,
        old_page_number=change.old_page_number,
        new_page_number=change.new_page_number,
        old_excerpt=change.old_excerpt,
        new_excerpt=change.new_excerpt,
        similarity=round(change.similarity, 4),
        assessment=assessment,
        latest_review=review,
    )


def _comparison_response(
    comparison: Comparison,
    severity: Severity | None = None,
    category: ChangeCategory | None = None,
    review_status: ReviewStatus | None = None,
) -> ComparisonResponse:
    changes = comparison.changes
    if severity:
        changes = [change for change in changes if change.assessment and change.assessment.severity == severity.value]
    if category:
        changes = [change for change in changes if change.assessment and change.assessment.category == category.value]
    if review_status:
        changes = [
            change
            for change in changes
            if change.review_decisions and change.review_decisions[-1].status == review_status.value
        ]
    return ComparisonResponse(
        id=comparison.id,
        baseline_version_id=comparison.baseline_version_id,
        candidate_version_id=comparison.candidate_version_id,
        status=comparison.status,
        duration_ms=comparison.duration_ms,
        created_at=comparison.created_at,
        changes=[_change_response(change) for change in changes],
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document_endpoint(document_id: str, db: DatabaseDependency) -> DocumentResponse:
    document = db.scalar(
        select(Document)
        .options(selectinload(Document.versions).selectinload(DocumentVersion.sections))
        .where(Document.id == document_id)
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return _document_response(document)


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document_endpoint(
    request: Request,
    db: DatabaseDependency,
    title: Annotated[str, Form(min_length=2, max_length=255)],
    version_label: Annotated[str, Form(min_length=1, max_length=80)] = "v1",
    file: UploadFile = File(...),
) -> DocumentResponse:
    settings = request.app.state.settings
    content = await _read_limited_upload(file, settings.max_upload_bytes)
    try:
        extracted = extract_document(file.filename or "upload.txt", content, settings.max_extracted_chars)
        document = create_document(
            db,
            title,
            VersionInput(version_label, extracted.text, original_filename=file.filename),
            settings.max_sections_per_version,
        )
        db.commit()
        document = db.scalar(
            select(Document)
            .options(selectinload(Document.versions).selectinload(DocumentVersion.sections))
            .where(Document.id == document.id)
        )
        return _document_response(document)
    except DocumentExtractionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/documents/{document_id}/versions",
    response_model=VersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_version_endpoint(
    document_id: str,
    request: Request,
    db: DatabaseDependency,
    version_label: Annotated[str, Form(min_length=1, max_length=80)],
    file: UploadFile = File(...),
) -> VersionResponse:
    settings = request.app.state.settings
    content = await _read_limited_upload(file, settings.max_upload_bytes)
    try:
        extracted = extract_document(file.filename or "upload.txt", content, settings.max_extracted_chars)
        version = create_version(
            db,
            document_id,
            VersionInput(version_label, extracted.text, original_filename=file.filename),
            settings.max_sections_per_version,
        )
        db.commit()
        db.refresh(version)
        return _version_response(version)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentExtractionError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="A version with this label already exists.") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/comparisons", response_model=ComparisonResponse, status_code=status.HTTP_201_CREATED)
def create_comparison_endpoint(payload: ComparisonCreateRequest, request: Request, db: DatabaseDependency) -> ComparisonResponse:
    try:
        comparison = create_or_get_comparison(
            db,
            payload.baseline_version_id,
            payload.candidate_version_id,
            request.app.state.assessment_service,
            request.app.state.settings.max_changed_sections,
            request.app.state.settings.max_assessment_calls,
        )
        db.commit()
        comparison = get_comparison(db, comparison.id)
        return _comparison_response(comparison)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidComparisonError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/comparisons/{comparison_id}", response_model=ComparisonResponse)
def get_comparison_endpoint(
    comparison_id: str,
    db: DatabaseDependency,
    severity: Severity | None = Query(default=None),
    category: ChangeCategory | None = Query(default=None),
    review_status: ReviewStatus | None = Query(default=None),
) -> ComparisonResponse:
    try:
        return _comparison_response(get_comparison(db, comparison_id), severity, category, review_status)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/changes/{change_id}/review", response_model=ReviewResponse)
def add_review_endpoint(change_id: str, payload: ReviewRequest, db: DatabaseDependency) -> ReviewResponse:
    try:
        decision = add_review_decision(db, change_id, payload.status, payload.note)
        db.commit()
        db.refresh(decision)
        return ReviewResponse(status=decision.status, note=decision.note, created_at=decision.created_at)
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/evaluations/run", response_model=EvaluationResponse)
def run_evaluation_endpoint(request: Request, db: DatabaseDependency) -> EvaluationResponse:
    # Evaluation must be reproducible and must never spend remote-model budget.
    metrics = run_benchmark(SafeAssessmentService(HeuristicAssessmentProvider()))
    run = store_evaluation_run(
        db,
        provider="heuristic",
        case_count=int(metrics["case_count"]),
        metrics_json=json.dumps(metrics),
    )
    db.commit()
    return EvaluationResponse(run_id=run.id, metrics=metrics)
