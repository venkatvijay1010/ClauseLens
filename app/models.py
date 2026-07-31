"""Persistent entities for document version comparison."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class ChangeType(str, enum.Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    MOVED = "moved"


class Severity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ChangeCategory(str, enum.Enum):
    DEADLINE = "deadline"
    PAYMENT = "payment"
    PRIVACY = "privacy"
    OBLIGATION = "obligation"
    TERMINATION = "termination"
    ELIGIBILITY = "eligibility"
    OTHER = "other"


class ReviewStatus(str, enum.Enum):
    PENDING = "pending"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    versions: Mapped[list[DocumentVersion]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.created_at"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_label", name="uq_document_version_label"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    extracted_character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="versions")
    sections: Mapped[list[Section]] = relationship(
        back_populates="version", cascade="all, delete-orphan", order_by="Section.ordinal"
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("version_id", "ordinal", name="uq_section_version_ordinal"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_heading: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    version: Mapped[DocumentVersion] = relationship(back_populates="sections")


class Comparison(Base):
    __tablename__ = "comparisons"
    __table_args__ = (
        UniqueConstraint("baseline_version_id", "candidate_version_id", name="uq_comparison_versions"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    baseline_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    candidate_version_id: Mapped[str] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    changes: Mapped[list[Change]] = relationship(
        back_populates="comparison", cascade="all, delete-orphan", order_by="Change.display_order"
    )


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    comparison_id: Mapped[str] = mapped_column(ForeignKey("comparisons.id", ondelete="CASCADE"), nullable=False)
    baseline_section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"))
    candidate_section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id"))
    display_order: Mapped[int] = mapped_column(Integer, nullable=False)
    change_type: Mapped[str] = mapped_column(String(20), nullable=False)
    old_heading: Mapped[str | None] = mapped_column(String(500))
    new_heading: Mapped[str | None] = mapped_column(String(500))
    old_page_number: Mapped[int | None] = mapped_column(Integer)
    new_page_number: Mapped[int | None] = mapped_column(Integer)
    old_text: Mapped[str | None] = mapped_column(Text)
    new_text: Mapped[str | None] = mapped_column(Text)
    old_excerpt: Mapped[str | None] = mapped_column(Text)
    new_excerpt: Mapped[str | None] = mapped_column(Text)
    similarity: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    comparison: Mapped[Comparison] = relationship(back_populates="changes")
    assessment: Mapped[ChangeAssessment | None] = relationship(
        back_populates="change", cascade="all, delete-orphan", uselist=False
    )
    review_decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="change", cascade="all, delete-orphan", order_by="ReviewDecision.sequence"
    )


class ChangeAssessment(Base):
    __tablename__ = "change_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    change_id: Mapped[str] = mapped_column(
        ForeignKey("changes.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    needs_human_review: Mapped[bool] = mapped_column(nullable=False, default=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    change: Mapped[Change] = relationship(back_populates="assessment")


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    __table_args__ = (UniqueConstraint("change_id", "sequence", name="uq_review_change_sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    change_id: Mapped[str] = mapped_column(ForeignKey("changes.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReviewStatus.PENDING.value)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    change: Mapped[Change] = relationship(back_populates="review_decisions")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
