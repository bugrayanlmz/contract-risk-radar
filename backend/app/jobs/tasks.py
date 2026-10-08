import asyncio
import logging
import time
from uuid import UUID

from procrastinate.jobs import Status
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.analysis.pdf import AnalysisError, extract_pdf
from app.analysis.pipeline import analyze_text
from app.config import get_settings
from app.db import session_factory
from app.jobs.app import get_queue
from app.models import AiFinding, AnalysisResult, Clause, Document, ImportantDate, utcnow
from app.providers.factory import create_provider
from app.storage.postgres import PostgresFileStorage

logger = logging.getLogger("radar.worker")
queue = get_queue()


class SupersededRun(Exception):
    pass


def active_run(document_id, run_id, job_id):
    return (
        Document.id == document_id,
        Document.run_id == run_id,
        Document.job_id == job_id,
        Document.status == "processing",
    )


async def run_analysis(
    document_id: UUID,
    run_id: UUID,
    job_id: int,
    factory: async_sessionmaker | None = None,
    provider=None,
):
    factory = factory or session_factory()
    started = time.monotonic()

    async def progress(stage):
        async with factory() as session, session.begin():
            changed = await session.execute(
                update(Document)
                .where(*active_run(document_id, run_id, job_id))
                .values(stage=stage, updated_at=utcnow())
            )
            if not changed.rowcount:
                raise SupersededRun()
        logger.info(
            "document=%s run=%s stage=%s elapsed=%.2f",
            document_id,
            run_id,
            stage,
            time.monotonic() - started,
        )

    try:
        async with factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(*active_run(document_id, run_id, job_id)).with_for_update()
            )
            if document is None:
                return
            document.started_at = utcnow()
            document.stage = "extracting_text"
            content = await PostgresFileStorage(session).get(document.file_id)
        text, warnings = await asyncio.to_thread(extract_pdf, content, get_settings())
        async with factory() as session, session.begin():
            await session.execute(
                update(Document)
                .where(*active_run(document_id, run_id, job_id))
                .values(extracted_text=text)
            )
        pipeline = await analyze_text(
            text, document_id, provider or create_provider(get_settings()), warnings, progress
        )
        await progress("saving")
        result = pipeline.response
        async with factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(*active_run(document_id, run_id, job_id)).with_for_update()
            )
            if document is None:
                return
            facts = result.facts
            analysis = AnalysisResult(
                document_id=document_id,
                run_id=run_id,
                start_date=facts.start_date,
                end_date=facts.end_date,
                monthly_rent=facts.monthly_rent.amount if facts.monthly_rent else None,
                rent_currency=facts.monthly_rent.currency if facts.monthly_rent else None,
                deposit_amount=facts.deposit_amount.amount if facts.deposit_amount else None,
                deposit_currency=facts.deposit_amount.currency if facts.deposit_amount else None,
                field_evidence={
                    **{
                        key: value.model_dump(mode="json")
                        for key, value in result.field_evidence.items()
                    },
                    "_warnings": facts.warnings,
                },
                overall_score=result.overall_score,
                language=facts.language,
                ai_overall_score=result.ai_overall_score,
                ai_review_status=result.ai_review_status,
                ai_rubric_version=result.ai_rubric_version,
                warnings=result.warnings,
                provider=result.provider,
                model=result.model,
                prompt_version=result.prompt_version,
                schema_version=result.schema_version,
                rules_version=result.rules_version,
                token_usage=pipeline.token_usage,
            )
            session.add(analysis)
            await session.flush()
            for position, finding in enumerate(result.clauses):
                session.add(
                    Clause(
                        id=finding.id,
                        analysis_id=analysis.id,
                        position=position,
                        category=finding.clause.category.value,
                        quote=finding.clause.quote,
                        quote_verified=finding.quote_verified,
                        explanation=finding.clause.explanation,
                        attributes=finding.clause.attributes.model_dump(mode="json"),
                        score=finding.score,
                        partial=finding.partial,
                        risk_factors=[
                            factor.model_dump(mode="json") for factor in finding.risk_factors
                        ],
                        warnings=finding.warnings,
                    )
                )
            for position, finding in enumerate(result.ai_findings):
                session.add(
                    AiFinding(
                        analysis_id=analysis.id,
                        position=position,
                        **finding.model_dump(mode="python", exclude={"related_category"}),
                        related_category=finding.related_category.value
                        if finding.related_category
                        else None,
                    )
                )
            await session.flush()
            for item in result.important_dates:
                session.add(
                    ImportantDate(
                        id=item.id,
                        analysis_id=analysis.id,
                        clause_id=item.clause_id,
                        kind=item.kind,
                        date=item.date,
                        basis=item.basis,
                        source_references=item.source_references,
                    )
                )
            document.status, document.stage = "completed", "completed"
            document.completed_at = utcnow()
            document.retryable = False
        logger.info(
            "document=%s run=%s completed provider=%s model=%s elapsed=%.2f",
            document_id,
            run_id,
            result.provider,
            result.model,
            time.monotonic() - started,
        )
    except SupersededRun:
        return
    except asyncio.CancelledError:

        async def mark_interrupted():
            async with factory() as session, session.begin():
                await session.execute(
                    update(Document)
                    .where(*active_run(document_id, run_id, job_id))
                    .values(
                        status="failed",
                        stage="failed",
                        error_code="WORKER_INTERRUPTED",
                        error_message="The worker stopped before analysis completed. Please retry.",
                        retryable=True,
                        updated_at=utcnow(),
                    )
                )

        await asyncio.shield(mark_interrupted())
        raise
    except Exception as exc:
        error = (
            exc
            if isinstance(exc, AnalysisError)
            else AnalysisError(
                "ANALYSIS_FAILED", "Analysis could not be completed. Please retry.", True
            )
        )
        async with factory() as session, session.begin():
            await session.execute(
                update(Document)
                .where(*active_run(document_id, run_id, job_id))
                .values(
                    status="failed",
                    stage="failed",
                    error_code=error.code,
                    error_message=error.message,
                    retryable=error.retryable,
                    updated_at=utcnow(),
                )
            )
        logger.error(
            "document=%s run=%s failed code=%s elapsed=%.2f",
            document_id,
            run_id,
            error.code,
            time.monotonic() - started,
        )
        raise error from None


@queue.task(name="analyze_document", queue="analysis", pass_context=True)
async def analyze_document(context, document_id: str, run_id: str):
    await run_analysis(UUID(document_id), UUID(run_id), context.job.id)


async def recover_stalled(app=queue, factory=None):
    factory = factory or session_factory()
    # Graceful shutdown records aborted queue jobs; also repair missed failure writes.
    async with factory() as session, session.begin():
        if session.bind.dialect.name == "postgresql":
            await session.execute(
                text("""
                    UPDATE documents AS document
                    SET status='failed', stage='failed', error_code='WORKER_INTERRUPTED',
                        error_message='The background job stopped before saving results. Please retry.',
                        retryable=true, updated_at=CURRENT_TIMESTAMP
                    FROM procrastinate_jobs AS job
                    WHERE document.job_id=job.id AND document.status='processing'
                      AND job.status IN ('failed', 'aborted', 'cancelled')
                """)
            )
    for job in await app.job_manager.get_stalled_jobs(
        task_name="analyze_document", seconds_since_heartbeat=60
    ):
        document_id, run_id = UUID(job.task_kwargs["document_id"]), UUID(job.task_kwargs["run_id"])
        retry_job = False
        terminal_status = Status.ABORTED
        async with factory() as session, session.begin():
            document = await session.scalar(
                select(Document).where(*active_run(document_id, run_id, job.id)).with_for_update()
            )
            if document is None:
                pass
            elif document.recovery_attempts >= 2:
                document.status, document.stage = "failed", "failed"
                document.error_code = "WORKER_INTERRUPTED"
                document.error_message = (
                    "The worker was repeatedly interrupted. Please retry analysis."
                )
                document.retryable = True
                terminal_status = Status.FAILED
            else:
                document.recovery_attempts += 1
                document.stage = "queued"
                retry_job = True
        # Commit app state first. If the queue operation fails, the next recovery
        # cycle still sees the stalled job and can finish it, releasing its lock.
        # Cancelling a 'doing' job without abort=True does not release that lock.
        if retry_job:
            await app.job_manager.retry_job(job)
        else:
            await app.job_manager.finish_job(job, status=terminal_status, delete_job=False)


@queue.periodic(cron="* * * * *")
@queue.task(name="recover_stalled", queue="maintenance", queueing_lock="recover_stalled")
async def recovery(timestamp):
    await recover_stalled()
