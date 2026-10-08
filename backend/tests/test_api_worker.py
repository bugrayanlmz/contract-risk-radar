import asyncio
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

import pytest
from reportlab.pdfgen.canvas import Canvas
from sqlalchemy import func, select, text

from app.analysis.pdf import AnalysisError
from app.jobs.app import enqueue_document, get_queue
from app.jobs.tasks import recover_stalled, run_analysis
from app.models import AnalysisResult, Clause, Document, StoredFile
from app.storage.postgres import PostgresFileStorage
from tests.helpers import TEXT, FakeProvider


async def register(client, email="demo@example.com"):
    response = await client.post(
        "/api/auth/register", json={"email": email, "password": "demo-password-123"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def upload(client, content):
    return await client.post(
        "/api/documents",
        files={"file": ("contract.pdf", content, "application/pdf")},
        data={"document_kind": "synthetic", "analysis_consent_confirmed": "true"},
    )


def fixture_pdf():
    stream = BytesIO()
    canvas = Canvas(stream)
    paragraph = canvas.beginText(20, 700)
    for line in TEXT.splitlines():
        paragraph.textLine(line)
    canvas.drawText(paragraph)
    canvas.showPage()
    canvas.save()
    return stream.getvalue()


async def test_auth_cookie_expiration_and_origin(client):
    assert (await client.get("/api/auth/me")).status_code == 401
    user = await register(client)
    assert (await client.get("/api/auth/me")).json()["id"] == user["id"]
    duplicate = await client.post(
        "/api/auth/register", json={"email": "DEMO@example.com", "password": "demo-password-123"}
    )
    assert duplicate.status_code == 409
    assert (
        await client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    ).status_code == 403
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    bad = await client.post(
        "/api/auth/login", json={"email": "demo@example.com", "password": "bad-password"}
    )
    assert bad.status_code == 401
    good = await client.post(
        "/api/auth/login", json={"email": "demo@example.com", "password": "demo-password-123"}
    )
    cookie = good.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Max-Age=3600" in cookie and "SameSite=lax" in cookie
    from datetime import datetime, timedelta, timezone

    import jwt

    from app.config import get_settings

    expired = jwt.encode(
        {
            "sub": user["id"],
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "iss": "contract-risk-radar",
            "aud": "radar-app",
        },
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    assert (
        await client.get("/api/auth/me", headers={"Cookie": f"radar_session={expired}"})
    ).status_code == 401


async def test_upload_confirmation_validation_rollback_and_ownership(
    client, factory, pdf_bytes, monkeypatch
):
    user = await register(client)

    async def enqueue_ok(session, document):
        return 42

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue_ok)
    assert (
        await client.post(
            "/api/documents",
            files={"file": ("bad.pdf", pdf_bytes)},
            data={"document_kind": "synthetic", "analysis_consent_confirmed": "false"},
        )
    ).status_code == 422
    assert (await upload(client, b"invalid")).status_code == 422
    response = await upload(client, pdf_bytes)
    assert response.status_code == 202, response.text
    document_id = response.json()["id"]
    assert (await client.get(f"/api/documents/{document_id}/results")).status_code == 409
    assert (await client.get(f"/api/documents/{document_id}/file")).content == pdf_bytes
    await register(client, "other@example.com")
    for suffix in ("", "/results", "/file"):
        assert (await client.get(f"/api/documents/{document_id}{suffix}")).status_code == 404
    assert (await client.post(f"/api/documents/{document_id}/retry")).status_code == 404
    assert (await client.get("/api/documents")).json() == []

    async def enqueue_failure(session, document):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue_failure)
    assert (await upload(client, pdf_bytes)).status_code == 500
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(Document)) == 1
        assert await session.scalar(select(func.count()).select_from(StoredFile)) == 1
        document = await session.scalar(select(Document))
        assert str(document.user_id) == user["id"]


async def test_worker_save_duplicate_and_retry(client, factory, monkeypatch):
    await register(client)
    count = 0

    async def enqueue_ok(session, document):
        nonlocal count
        count += 1
        return count

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue_ok)
    data = (await upload(client, fixture_pdf())).json()
    document_id = UUID(data["id"])
    async with factory() as session:
        document = await session.get(Document, document_id)
        run_id = document.run_id
    await run_analysis(document_id, run_id, 1, factory, FakeProvider())
    response = await client.get(f"/api/documents/{document_id}/results")
    assert response.status_code == 200, response.text
    assert response.json()["overall_score"] == 4
    assert any(
        item["kind"] == "renewal_notice_deadline" for item in response.json()["important_dates"]
    )
    await run_analysis(document_id, run_id, 1, factory, FakeProvider())
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(AnalysisResult)) == 1
        assert await session.scalar(select(func.count()).select_from(Clause)) == 1

    # A separate upload exercises failure -> manual retry -> stale task -> completion.
    failed_id = UUID((await upload(client, fixture_pdf())).json()["id"])
    async with factory() as session:
        old = await session.get(Document, failed_id)
        old_run, old_job = old.run_id, old.job_id
    with pytest.raises(AnalysisError):
        await run_analysis(failed_id, old_run, old_job, factory, FakeProvider(fail=True))
    assert (await client.get(f"/api/documents/{failed_id}")).json()["status"] == "failed"
    assert (await client.post(f"/api/documents/{failed_id}/retry")).status_code == 202
    assert (await client.post(f"/api/documents/{failed_id}/retry")).status_code == 409
    await run_analysis(failed_id, old_run, old_job, factory, FakeProvider())
    assert (await client.get(f"/api/documents/{failed_id}")).json()["status"] == "processing"
    async with factory() as session:
        new = await session.get(Document, failed_id)
        new_run, new_job = new.run_id, new.job_id
    await run_analysis(failed_id, new_run, new_job, factory, FakeProvider())
    assert (await client.get(f"/api/documents/{failed_id}")).json()["status"] == "completed"


async def test_scanned_pdf_fails_readably_without_retry(client, factory, scanned_pdf, monkeypatch):
    await register(client)

    async def enqueue_ok(session, document):
        return 1

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue_ok)
    document_id = UUID((await upload(client, scanned_pdf)).json()["id"])
    async with factory() as session:
        run_id = (await session.get(Document, document_id)).run_id
    with pytest.raises(AnalysisError, match="no readable text layer"):
        await run_analysis(document_id, run_id, 1, factory, FakeProvider())
    result = (await client.get(f"/api/documents/{document_id}")).json()
    assert result["error_code"] == "NO_TEXT_LAYER" and not result["retryable"]
    assert (await client.post(f"/api/documents/{document_id}/retry")).status_code == 409


@pytest.mark.postgres
async def test_real_queue_transaction_and_worker(client, factory, monkeypatch):
    await register(client)
    queue = get_queue()
    await queue.open_async()
    try:
        data = await upload(client, fixture_pdf())
        assert data.status_code == 202, data.text
        document_id = UUID(data.json()["id"])
        async with factory() as session:
            document = await session.get(Document, document_id)
            row = (
                await session.execute(
                    text("SELECT args FROM procrastinate_jobs WHERE id=:id"),
                    {"id": document.job_id},
                )
            ).scalar_one()
            assert row["document_id"] == str(document_id)
        monkeypatch.setattr("app.jobs.tasks.session_factory", lambda: factory)
        monkeypatch.setattr("app.jobs.tasks.create_provider", lambda settings: FakeProvider())
        await queue.run_worker_async(wait=False, queues=["analysis"], concurrency=1)
        assert (await client.get(f"/api/documents/{document_id}")).json()["status"] == "completed"

        # Deferral succeeds, then failure before commit must roll back PDF, document, and job.
        async def fail_after_enqueue(session, document):
            await enqueue_document(session, document)
            raise RuntimeError("Simulated commit boundary failure")

        monkeypatch.setattr("app.api.documents.enqueue_document", fail_after_enqueue)
        async with factory() as session:
            before = await session.scalar(text("SELECT count(*) FROM procrastinate_jobs"))
        assert (await upload(client, fixture_pdf())).status_code == 500
        async with factory() as session:
            assert await session.scalar(text("SELECT count(*) FROM procrastinate_jobs")) == before
            assert await session.scalar(select(func.count()).select_from(Document)) == 1
            assert await session.scalar(select(func.count()).select_from(StoredFile)) == 1
    finally:
        await queue.close_async()


@pytest.mark.postgres
async def test_concurrent_retry_serializes(client, factory, monkeypatch):
    await register(client)

    async def enqueue_ok(session, document):
        return 1

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue_ok)
    document_id = UUID((await upload(client, fixture_pdf())).json()["id"])
    async with factory() as session, session.begin():
        document = await session.get(Document, document_id)
        document.status, document.stage, document.retryable = "failed", "failed", True
    responses = await asyncio.gather(
        client.post(f"/api/documents/{document_id}/retry"),
        client.post(f"/api/documents/{document_id}/retry"),
    )
    assert sorted(response.status_code for response in responses) == [202, 409]


async def test_stalled_recovery_is_bounded(client, factory, monkeypatch):
    await register(client)

    async def enqueue_ok(session, document):
        return 9

    monkeypatch.setattr("app.api.documents.enqueue_document", enqueue_ok)
    document_id = UUID((await upload(client, fixture_pdf())).json()["id"])
    async with factory() as session:
        run_id = (await session.get(Document, document_id)).run_id
    job = SimpleNamespace(
        id=9, task_kwargs={"document_id": str(document_id), "run_id": str(run_id)}
    )

    class Manager:
        retries = 0
        cancellations = 0

        async def get_stalled_jobs(self, **kwargs):
            return [job]

        async def retry_job(self, job):
            self.retries += 1

        async def cancel_job_by_id_async(self, job_id):
            self.cancellations += 1

        async def finish_job(self, job, status, delete_job):
            self.cancellations += 1

    manager = Manager()
    queue = SimpleNamespace(job_manager=manager)
    for _ in range(3):
        await recover_stalled(queue, factory)
    status = (await client.get(f"/api/documents/{document_id}")).json()
    assert manager.retries == 2 and status["status"] == "failed" and status["retryable"]


async def test_storage_uses_caller_transaction(factory, pdf_bytes):
    async with factory() as session:
        file_id = await PostgresFileStorage(session).put(pdf_bytes, "application/pdf")
        assert await PostgresFileStorage(session).get(file_id) == pdf_bytes
        await session.rollback()
    async with factory() as session:
        assert await session.get(StoredFile, file_id) is None


@pytest.mark.postgres
async def test_exhausted_stalled_job_releases_real_execution_lock(client, factory, monkeypatch):
    await register(client)
    queue = get_queue()
    await queue.open_async()
    try:
        document_id = UUID((await upload(client, fixture_pdf())).json()["id"])
        async with factory() as session, session.begin():
            document = await session.get(Document, document_id)
            document.recovery_attempts = 2
            old_job = document.job_id
            await session.execute(
                text("UPDATE procrastinate_jobs SET status='doing', worker_id=NULL WHERE id=:id"),
                {"id": old_job},
            )
        await recover_stalled(queue, factory)
        async with factory() as session:
            assert (
                await session.scalar(
                    text("SELECT status FROM procrastinate_jobs WHERE id=:id"), {"id": old_job}
                )
                == "failed"
            )
        assert (await client.post(f"/api/documents/{document_id}/retry")).status_code == 202
        monkeypatch.setattr("app.jobs.tasks.session_factory", lambda: factory)
        monkeypatch.setattr("app.jobs.tasks.create_provider", lambda settings: FakeProvider())
        await queue.run_worker_async(wait=False, queues=["analysis"], concurrency=1)
        assert (await client.get(f"/api/documents/{document_id}")).json()["status"] == "completed"
    finally:
        await queue.close_async()


@pytest.mark.postgres
async def test_worker_shutdown_and_restart(client, factory, monkeypatch):
    await register(client)
    queue = get_queue()
    await queue.open_async()
    worker = None
    started = asyncio.Event()

    class InterruptedProvider(FakeProvider):
        async def extract(self, *args, **kwargs):
            started.set()
            await asyncio.Event().wait()

    try:
        document_id = UUID((await upload(client, fixture_pdf())).json()["id"])
        monkeypatch.setattr("app.jobs.tasks.session_factory", lambda: factory)
        monkeypatch.setattr(
            "app.jobs.tasks.create_provider", lambda settings: InterruptedProvider()
        )
        worker = asyncio.create_task(
            queue.run_worker_async(
                wait=False, queues=["analysis"], concurrency=1, shutdown_graceful_timeout=0.05
            )
        )
        await asyncio.wait_for(started.wait(), timeout=5)
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(worker, timeout=5)
        status = (await client.get(f"/api/documents/{document_id}")).json()
        assert status["status"] == "failed" and status["retryable"]
        assert status["error_code"] == "WORKER_INTERRUPTED"

        # Simulate a missed application write after the native job was aborted.
        async with factory() as session, session.begin():
            document = await session.get(Document, document_id)
            native_status = await session.scalar(
                text("SELECT status FROM procrastinate_jobs WHERE id=:id"),
                {"id": document.job_id},
            )
            assert native_status == "aborted"
            document.status, document.stage = "processing", "extracting_clauses"
        await recover_stalled(queue, factory)
        assert (await client.get(f"/api/documents/{document_id}")).json()["status"] == "failed"
        assert (await client.post(f"/api/documents/{document_id}/retry")).status_code == 202
        monkeypatch.setattr("app.jobs.tasks.create_provider", lambda settings: FakeProvider())
        await queue.run_worker_async(wait=False, queues=["analysis"], concurrency=1)
        assert (await client.get(f"/api/documents/{document_id}")).json()["status"] == "completed"
    finally:
        if worker is not None and not worker.done():
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await queue.close_async()
