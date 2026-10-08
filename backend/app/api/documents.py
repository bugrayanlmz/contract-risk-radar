import json
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.analysis.pdf import validate_pdf
from app.config import get_settings
from app.db import get_session
from app.jobs.app import enqueue_document
from app.models import Document, User
from app.schemas.responses import AnalysisResponse, DocumentResponse, SampleResponse
from app.services.auth import current_user
from app.services.documents import owned_document, read_results
from app.storage.postgres import PostgresFileStorage

router = APIRouter(tags=["documents"])


async def store_document(content, filename, user, session, document_kind="synthetic"):
    await run_in_threadpool(validate_pdf, content, get_settings())
    # current_user may already have started a read transaction on this session.
    try:
        file_id = await PostgresFileStorage(session).put(content, "application/pdf")
        document = Document(
            user_id=user.id,
            file_id=file_id,
            filename=Path(filename or "contract.pdf").name[:255],
            document_kind=document_kind,
        )
        session.add(document)
        await session.flush()
        document.job_id = await enqueue_document(session, document)
        await session.commit()
        return document
    except Exception:
        await session.rollback()
        raise


@router.post(
    "/documents", response_model=DocumentResponse, status_code=202, operation_id="uploadDocument"
)
async def upload_document(
    file: UploadFile = File(),
    document_kind: Literal["synthetic", "real"] = Form(),
    analysis_consent_confirmed: bool = Form(),
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    if not analysis_consent_confirmed:
        raise HTTPException(
            422,
            detail={
                "code": "CONFIRMATION_REQUIRED",
                "message": "Confirm you are authorized to upload this contract and send its text to the configured AI provider.",
            },
        )
    if document_kind == "real" and not get_settings().real_documents_allowed:
        raise HTTPException(
            403,
            detail={
                "code": "REAL_DOCUMENTS_DISABLED",
                "message": "Real documents are enabled only in an explicitly configured development environment.",
            },
        )
    try:
        content = await file.read(get_settings().max_upload_bytes + 1)
    finally:
        await file.close()
    return await store_document(content, file.filename, user, session, document_kind)


@router.get("/documents", response_model=list[DocumentResponse], operation_id="listDocuments")
async def list_documents(
    user: User = Depends(current_user), session: AsyncSession = Depends(get_session)
):
    return (
        await session.scalars(
            select(Document)
            .where(Document.user_id == user.id)
            .order_by(Document.created_at.desc())
            .limit(100)
        )
    ).all()


@router.get("/documents/{document_id}", response_model=DocumentResponse, operation_id="getDocument")
async def get_document(
    document_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    return await owned_document(session, document_id, user.id)


@router.get(
    "/documents/{document_id}/results", response_model=AnalysisResponse, operation_id="getResults"
)
async def results(
    document_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    return await read_results(session, await owned_document(session, document_id, user.id))


@router.get(
    "/documents/{document_id}/file",
    response_class=Response,
    operation_id="downloadDocument",
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def download(
    document_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    document = await owned_document(session, document_id, user.id)
    return Response(
        await PostgresFileStorage(session).get(document.file_id),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/documents/{document_id}/retry",
    response_model=DocumentResponse,
    status_code=202,
    operation_id="retryDocument",
)
async def retry(
    document_id: UUID,
    user: User = Depends(current_user),
    session: AsyncSession = Depends(get_session),
):
    document = await owned_document(session, document_id, user.id, lock=True)
    if document.status != "failed" or not document.retryable:
        raise HTTPException(
            409,
            detail={
                "code": "NOT_RETRYABLE",
                "message": "Only retryable failed analyses can be retried.",
            },
        )
    try:
        document.run_id = uuid4()
        document.status, document.stage = "processing", "queued"
        document.error_code = document.error_message = None
        document.started_at = document.completed_at = None
        document.retryable = False
        document.recovery_attempts = 0
        document.job_id = await enqueue_document(session, document)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return document


def sample_manifest() -> list[dict]:
    path = get_settings().samples_dir / "manifest.json"
    return json.loads(path.read_text()) if path.exists() else []


@router.get("/samples", response_model=list[SampleResponse], operation_id="listSamples")
async def samples(user: User = Depends(current_user)):
    return sample_manifest()


@router.get(
    "/samples/{sample_id}/file",
    response_class=Response,
    operation_id="downloadSample",
    responses={
        200: {"content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}}
    },
)
async def sample_file(sample_id: str, user: User = Depends(current_user)):
    if sample_id not in {sample["id"] for sample in sample_manifest()}:
        raise HTTPException(404, detail={"code": "NOT_FOUND", "message": "Sample not found."})
    return Response(
        (get_settings().samples_dir / f"{sample_id}.pdf").read_bytes(), media_type="application/pdf"
    )
