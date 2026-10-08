from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.schemas.extraction import AiFinding, Category, ContractFacts, ExtractedClause


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    email: str


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    document_kind: Literal["synthetic", "real"]
    status: Literal["processing", "completed", "failed"]
    stage: Literal[
        "queued",
        "extracting_text",
        "extracting_clauses",
        "verifying",
        "scoring",
        "reviewing_additional_risks",
        "saving",
        "completed",
        "failed",
    ]
    error_code: str | None
    error_message: str | None
    retryable: bool
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None


class RiskFactor(BaseModel):
    code: str
    severity: int = Field(ge=1, le=5)
    explanation: str
    inputs: dict[str, str | int | bool | None]


class ClauseResult(BaseModel):
    id: UUID
    clause: ExtractedClause
    quote_verified: bool
    score: int | None = Field(ge=1, le=5)
    partial: bool
    risk_factors: list[RiskFactor]
    warnings: list[str]


class FieldEvidenceResult(BaseModel):
    quote: str | None
    verified: bool


class AiFindingResult(AiFinding):
    id: UUID
    quote_verified: bool
    score: int | None = Field(ge=1, le=5)
    warnings: list[str]


class CapabilitiesResponse(BaseModel):
    supported_languages: list[Literal["english", "german"]]
    real_documents_allowed: bool


class ImportantDateResponse(BaseModel):
    id: UUID
    clause_id: UUID | None
    kind: str
    date: date
    basis: str
    source_references: list[str]


class AnalysisResponse(BaseModel):
    document_id: UUID
    facts: ContractFacts
    field_evidence: dict[str, FieldEvidenceResult]
    overall_score: int | None = Field(ge=1, le=5)
    ai_overall_score: int | None = Field(ge=1, le=5)
    ai_review_status: Literal["not_run", "completed"]
    ai_rubric_version: str | None
    ai_findings: list[AiFindingResult]
    clauses: list[ClauseResult]
    important_dates: list[ImportantDateResponse]
    categories_not_found: list[Category]
    warnings: list[str]
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    rules_version: str


class ApiErrorDetail(BaseModel):
    code: str
    message: str


class ApiError(BaseModel):
    error: ApiErrorDetail


class SampleResponse(BaseModel):
    id: str
    name: str
    description: str
