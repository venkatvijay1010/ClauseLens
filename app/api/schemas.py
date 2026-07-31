"""Public HTTP contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models import ChangeCategory, ChangeType, ReviewStatus, Severity


class DocumentCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    version_label: str = Field(default="v1", min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=500_000)


class VersionCreateRequest(BaseModel):
    version_label: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=500_000)


class VersionResponse(BaseModel):
    id: str
    version_label: str
    original_filename: str | None
    extracted_character_count: int
    section_count: int
    created_at: datetime | None


class DocumentResponse(BaseModel):
    id: str
    title: str
    versions: list[VersionResponse]


class ComparisonCreateRequest(BaseModel):
    baseline_version_id: str
    candidate_version_id: str


class ReviewRequest(BaseModel):
    status: ReviewStatus
    note: str | None = Field(default=None, max_length=2000)


class AssessmentResponse(BaseModel):
    category: ChangeCategory
    severity: Severity
    summary: str
    rationale: str
    needs_human_review: bool
    provider: str
    validation_status: str


class ReviewResponse(BaseModel):
    status: ReviewStatus
    note: str | None
    created_at: datetime | None


class ChangeResponse(BaseModel):
    id: str
    display_order: int
    change_type: ChangeType
    old_heading: str | None
    new_heading: str | None
    old_page_number: int | None
    new_page_number: int | None
    old_excerpt: str | None
    new_excerpt: str | None
    similarity: float
    assessment: AssessmentResponse | None
    latest_review: ReviewResponse | None


class ComparisonResponse(BaseModel):
    id: str
    baseline_version_id: str
    candidate_version_id: str
    status: str
    duration_ms: int
    created_at: datetime | None
    changes: list[ChangeResponse]


class EvaluationResponse(BaseModel):
    run_id: str
    metrics: dict[str, object]
