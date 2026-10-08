from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AiFinding, AnalysisResult, Clause, Document, ImportantDate
from app.schemas.extraction import Category, ContractFacts, Money
from app.schemas.responses import (
    AiFindingResult,
    AnalysisResponse,
    ClauseResult,
    ImportantDateResponse,
)


async def owned_document(
    session: AsyncSession, document_id: UUID, user_id: UUID, lock: bool = False
) -> Document:
    statement = select(Document).where(Document.id == document_id, Document.user_id == user_id)
    if lock:
        statement = statement.with_for_update()
    document = await session.scalar(statement)
    if document is None:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Document not found."})
    return document


async def read_results(session: AsyncSession, document: Document) -> AnalysisResponse:
    if document.status != "completed":
        raise HTTPException(
            409,
            detail={
                "code": "RESULTS_UNAVAILABLE",
                "message": "Results are available after analysis completes.",
            },
        )
    result = await session.scalar(
        select(AnalysisResult).where(
            AnalysisResult.document_id == document.id, AnalysisResult.run_id == document.run_id
        )
    )
    if result is None:
        raise HTTPException(
            409, detail={"code": "RESULTS_UNAVAILABLE", "message": "Results are not available yet."}
        )
    evidence = {k: v for k, v in result.field_evidence.items() if not k.startswith("_")}
    facts = ContractFacts(
        start_date=result.start_date,
        end_date=result.end_date,
        monthly_rent=Money(amount=result.monthly_rent, currency=result.rent_currency)
        if result.monthly_rent is not None
        else None,
        deposit_amount=Money(amount=result.deposit_amount, currency=result.deposit_currency)
        if result.deposit_amount is not None
        else None,
        evidence={key: value["quote"] for key, value in evidence.items()},
        warnings=result.field_evidence.get("_warnings", []),
        contract_type="residential_rental",
        language=result.language,
    )
    rows = (
        await session.scalars(
            select(Clause).where(Clause.analysis_id == result.id).order_by(Clause.position)
        )
    ).all()
    clauses = [
        ClauseResult(
            id=row.id,
            clause={
                "category": row.category,
                "quote": row.quote,
                "explanation": row.explanation,
                "attributes": row.attributes,
            },
            quote_verified=row.quote_verified,
            score=row.score,
            partial=row.partial,
            risk_factors=row.risk_factors,
            warnings=row.warnings,
        )
        for row in rows
    ]
    date_rows = (
        await session.scalars(
            select(ImportantDate)
            .where(ImportantDate.analysis_id == result.id)
            .order_by(ImportantDate.date)
        )
    ).all()
    ai_rows = (
        await session.scalars(
            select(AiFinding).where(AiFinding.analysis_id == result.id).order_by(AiFinding.position)
        )
    ).all()
    return AnalysisResponse(
        document_id=document.id,
        facts=facts,
        field_evidence=evidence,
        overall_score=result.overall_score,
        ai_overall_score=result.ai_overall_score,
        ai_review_status=result.ai_review_status,
        ai_rubric_version=result.ai_rubric_version,
        ai_findings=[AiFindingResult.model_validate(row, from_attributes=True) for row in ai_rows],
        clauses=clauses,
        important_dates=[
            ImportantDateResponse(
                id=row.id,
                clause_id=row.clause_id,
                kind=row.kind,
                date=row.date,
                basis=row.basis,
                source_references=row.source_references,
            )
            for row in date_rows
        ],
        categories_not_found=[
            category for category in Category if category not in {row.category for row in rows}
        ],
        warnings=result.warnings,
        provider=result.provider,
        model=result.model,
        prompt_version=result.prompt_version,
        schema_version=result.schema_version,
        rules_version=result.rules_version,
    )
