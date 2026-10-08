import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


Json = JSON().with_variant(JSONB(), "postgresql")


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StoredFile(Base):
    __tablename__ = "stored_files"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    __table_args__ = (CheckConstraint("size_bytes > 0", name="positive_file_size"),)


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stored_files.id"), unique=True)
    filename: Mapped[str] = mapped_column(String(255))
    document_kind: Mapped[str] = mapped_column(
        String(20), default="synthetic", server_default="synthetic"
    )
    extracted_text: Mapped[str | None] = mapped_column(Text, deferred=True)
    status: Mapped[str] = mapped_column(String(20), default="processing")
    stage: Mapped[str] = mapped_column(String(30), default="queued")
    run_id: Mapped[uuid.UUID] = mapped_column(default=uuid.uuid4)
    job_id: Mapped[int | None] = mapped_column(BigInteger)
    recovery_attempts: Mapped[int] = mapped_column(default=0)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_documents_owner_created", "user_id", "created_at"),
        CheckConstraint("status IN ('processing', 'completed', 'failed')", name="document_status"),
        CheckConstraint("document_kind IN ('synthetic', 'real')", name="document_kind"),
    )


class AnalysisResult(Base):
    __tablename__ = "analysis_results"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), unique=True
    )
    run_id: Mapped[uuid.UUID]
    start_date: Mapped[date | None]
    end_date: Mapped[date | None]
    monthly_rent: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    rent_currency: Mapped[str | None] = mapped_column(String(3))
    deposit_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    deposit_currency: Mapped[str | None] = mapped_column(String(3))
    field_evidence: Mapped[dict] = mapped_column(Json)
    overall_score: Mapped[int | None]
    language: Mapped[str] = mapped_column(String(20), default="english", server_default="english")
    ai_overall_score: Mapped[int | None]
    ai_review_status: Mapped[str] = mapped_column(
        String(20), default="not_run", server_default="not_run"
    )
    ai_rubric_version: Mapped[str | None] = mapped_column(String(20))
    warnings: Mapped[list] = mapped_column(Json)
    provider: Mapped[str] = mapped_column(String(30))
    model: Mapped[str] = mapped_column(String(120))
    prompt_version: Mapped[str] = mapped_column(String(20))
    schema_version: Mapped[str] = mapped_column(String(20))
    rules_version: Mapped[str] = mapped_column(String(20))
    token_usage: Mapped[dict] = mapped_column(Json)
    __table_args__ = (
        CheckConstraint("overall_score BETWEEN 1 AND 5", name="overall_score_range"),
        CheckConstraint("ai_overall_score BETWEEN 1 AND 5", name="ai_overall_score_range"),
        CheckConstraint("language IN ('english', 'german')", name="analysis_language"),
        CheckConstraint("ai_review_status IN ('not_run', 'completed')", name="ai_review_status"),
    )


class AiFinding(Base):
    __tablename__ = "ai_findings"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    title: Mapped[str] = mapped_column(String(120))
    related_category: Mapped[str | None] = mapped_column(String(30))
    quote: Mapped[str] = mapped_column(Text)
    quote_verified: Mapped[bool]
    explanation: Mapped[str] = mapped_column(Text)
    model_score: Mapped[int]
    score: Mapped[int | None]
    rationale: Mapped[str] = mapped_column(Text)
    uncertainties: Mapped[list] = mapped_column(Json)
    warnings: Mapped[list] = mapped_column(Json)
    __table_args__ = (
        CheckConstraint("model_score BETWEEN 1 AND 5", name="ai_model_score_range"),
        CheckConstraint("score BETWEEN 1 AND 5", name="ai_finding_score_range"),
        CheckConstraint("quote_verified OR score IS NULL", name="ai_unverified_not_scored"),
    )


class Clause(Base):
    __tablename__ = "clauses"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    category: Mapped[str] = mapped_column(String(30))
    quote: Mapped[str] = mapped_column(Text)
    quote_verified: Mapped[bool]
    explanation: Mapped[str] = mapped_column(Text)
    attributes: Mapped[dict] = mapped_column(Json)
    score: Mapped[int | None]
    partial: Mapped[bool]
    risk_factors: Mapped[list] = mapped_column(Json)
    warnings: Mapped[list] = mapped_column(Json)
    __table_args__ = (CheckConstraint("score BETWEEN 1 AND 5", name="clause_score_range"),)


class ImportantDate(Base):
    __tablename__ = "important_dates"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("analysis_results.id", ondelete="CASCADE"), index=True
    )
    clause_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("clauses.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(40))
    date: Mapped[date]
    basis: Mapped[str] = mapped_column(Text)
    source_references: Mapped[list] = mapped_column(Json)
